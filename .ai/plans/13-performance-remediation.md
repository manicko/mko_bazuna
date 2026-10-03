---
plan_id: "13-performance-remediation"
phase: "13"
phase_name: "Performance — Query, Cache, Write-Path and Observability"
source_report: ".ai/audit/99-validation/13-performance-validated-findings.md"
source_findings: ".ai/audit/13-performance/findings.md (deleted in the working tree — not an input)"
code_context: ".ai/tmp/code-context-phase13.md"
date: "2026-09-29"
planner: "Planner (subagent)"
anchor_commit: "ba23277"
report_anchor_commit: "e57f8f8"
status: "planned"
findings_in_scope: 15
findings_still_exist: 15
findings_partial: 0
findings_merged: 1
findings_already_fixed: 0
findings_rejected: 0
val_findings_open: 4
blocks: 12
---

# Execution Plan — Phase 13 Remediation (Performance)

## 0. Header, provenance and scope statement

### 0.1 Provenance

| | |
|---|---|
| **Phase** | 13 — Performance |
| **Source (authoritative)** | `.ai/audit/99-validation/13-performance-validated-findings.md` (1 694 lines, 15 `PERF-` findings + 4 `VAL-` items) |
| **Code context** | `.ai/tmp/code-context-phase13.md` (1 372 lines) |
| **Deleted input** | `.ai/audit/13-performance/findings.md` — **gone from the tree.** It is *not* an input. `VAL-002` instructed that its six non-existent quotations be corrected "in the source report"; that file no longer exists, so the correction is recorded **here** (§0.4, C-6) and not there |
| **This plan's anchor** | `ba23277` |
| **The report's anchor** | `e57f8f8` |
| **Date** | 2026-09-29 |

**The anchor has drifted three times while this plan was being written:** `6413df5` → `e57f8f8`
→ `d42f778` → `ba23277`. All three intervening commits are **phase 02 settings work**
(`CFG-004` half A, `CFG-007` + `CFG-010`, `CFG-003`) and **none touches a phase-13 file**:
no `search.py`, no `context_processors.py`, no `locustfile.py`, no `ci.yml`, no cache service,
no management command, no test file on this plan's tripwire list. **The phase-13 finding set
is therefore unchanged by the drift**, and every finding this plan acts on was re-verified in
the tree at `ba23277` (§0.2.4). The Implementor must still take their own
`git rev-parse --short HEAD` before the first block, and re-read immediately before editing any
file listed in §5.3.

**The tree is the authority.** Where the validated report and the tree disagree, §0.4 says so
and this plan follows the tree.

**`PERF-` is a live, ambiguous namespace — read this before citing a single finding ID.**
Six shipped locations already carry a `13-PERF-00N` string, and **none of them means what this
phase's `PERF-00N` means**:

| Shipped string | Shipped location | What it means there | What this plan's `PERF-00N` means |
|---|---|---|---|
| `13-PERF-001` | `apps/search/tests/test_search_slo.py` module docstring; `docs/ops/prometheus-slo-alerts.yaml` header; `.github/workflows/ci.yml` (`load-test`, SLO step comment) | the **SLO-constants + latency-regression guard** | the **broken locust p95 CI gate** |
| `13-PERF-002` | `Makefile` section header "Performance (PERF-002)"; `apps/lookups/tests/test_lookup_cache_swr.py` | **single-flight stampede guard** on the lookup cache | **`?features=` memory blowup** (merged out — §6.2) |
| `13-PERF-003` | `apps/lookups/tests/test_lookup_cache_swr.py`; `apps/search/tests/test_search_cache.py` | **stale-serve SWR** behaviour | **`rollup_daily_metrics` write loop** |
| `13-PERF-004` | `apps/search/tests/test_search_query_count.py` | **N+1 query-count guard** for `/search/` | **`render_trust_badge` prefetch detection** |
| `13-PERF-006` | `docs/architecture/cache-strategy.md` front-matter and Purpose; `apps/lookups/tests/test_cache_key_convention.py`; `backend/tests/test_cache_key_convention.py` | the **cache-key naming convention** | **search-cache count recomputation at the cap** |
| `13-PERF-007` | `apps/categories/tests/test_submenu_swr.py` | **category-submenu SWR** behaviour | **cold-miss single-flight exposure** |

**Citation convention adopted by this plan (mandatory in every commit body, comment and test
docstring):** write `PERF-0NN (validated 2026-09)` for a finding ID, and
`13-PERF-0NN (pre-existing, see .ai/audit/99-validation/13-performance-validated-findings.md §0.1)`
for the *shipped* strings above. A bare `13-PERF-004` in a new comment is **ambiguous and is
rejected in review.**

**Reservation.** The *sweep* of these six strings is **phase 03 BLOCK 11's**, and phase 03
**forbids other phases from touching them** — the strings are phase-08/10/11 deliverables that
happen to share a prefix. **Phase 13 does not rename, retag or clean any of them** (§5.2 item 1,
§6.3 item 1). Phase 13's obligation is to *not make the collision worse*, which is why the
convention above exists.

### 0.2 Evidence basis — read this before executing any block

#### 0.2.1 What the validated report establishes

Fifteen findings, all still present at `e57f8f8` and re-verified at `ba23277`
(§0.2.4). Verdicts: **5 CONFIRMED · 9 ADJUSTED · 1 MERGED · 0 REJECTED** · 1 half-finding
rejected (`PERF-011`'s capacity limb) · 2 rejected recommendations (`PERF-006` fix #3
`work_mem`; `PERF-011` recommendation #2 `workers`) · 1 rejected remediation
(`PERF-009`'s `prefetch_related("children")`). Severity moved
**1 CRITICAL · 5 HIGH · 6 MEDIUM · 3 LOW → 0 CRITICAL · 2 HIGH · 8 MEDIUM · 5 LOW.**

#### 0.2.2 The three rules that constrain every block in this plan

These come from the code context §11 and from the project's own stated philosophy. They are
**binding on every Implementor**, and they are the reason several tempting one-liners are gated
rather than shipped.

1. **Correctness and clarity must never be traded for speed.** A change that alters semantics —
   a stale read, a dropped `COUNT(*)`, a changed result ordering, a cache an invariant depends
   on, a displayed count — **is not a performance change.** Concretely and immediately:
   `results_truncated` and the hot-path FTS `COUNT(*)` behaviour are **product-visible**; the
   `?features=` AND-of-features semantics must be preserved exactly by any join collapse; and
   `_QUERY_BOUND` must **never** be weakened to accommodate a fix. Every such candidate is in
   §6, not in a block.
2. **Production code is king.** A test that pins a defect gets the defect fixed, not the code
   bent — and where a tripwire genuinely pins a defect (`_QUERY_BOUND = 100`, widened to
   absorb two known N+1s), the order is **fix the defect → measure the new inventory → re-derive
   the number → change the test**, all inside one commit's story. This plan pre-authorises
   exactly **one** such change — BLOCK 5's `_QUERY_BOUND` — and it is behind gate **Q7**.
3. **Avoid overengineering; prefer the simple, obvious, maintainable solution.** Already
   rejected upstream and confirmed here: raising `work_mem` (a per-node × per-worker ×
   per-connection multiplier against a 1 GB `DB_MEM_LIMIT` that ships to production, and
   unnecessary once `PERF-006` #1 lands); raising gunicorn `workers` (the CPU budget is
   `WEB_CPUS = 1.5`, so "near the core count" means 1–2 — *fewer* than today's 3); and
   `prefetch_related("children")` against `mptt`'s `get_children` (a no-op).
   **Every accepted remediation in this plan reuses a shipped primitive** — `bulk_create`,
   `Case`/`When`, `Exists`, the existing SWR helper, the existing version-bump mechanism.
   A block that introduces a new abstraction must justify it in its commit body against this
   rule.

#### 0.2.3 Every latency, row-count and `EXPLAIN` claim is **unverified**, with its command

Nothing in this plan ships a "faster" claim without one of the two proofs §3 demands
(**before/after numbers**, or a **tripwire test** that fails when the regression returns). The
validated report's own numbers are a **mix**: some are runtime-verified by the validator, some
are the original auditor's and were re-derived, and some are the original auditor's alone and
are **not portable**. The following table is the evidence basis. **Row 5 is the load-bearing
caution: the single number that made `PERF-006` a HIGH is a single-sample measurement that the
validator's own `VAL-003` rule forbids quoting.**

| # | Claim | Status | Exact verification command |
|---|---|---|---|
| 1 | `?features=` cost curve 10 → 1.31 s … 60 → 19.90 s, then `signal 9` | **Not re-measured.** Needs a private DB under a real `mem_limit` | Private `postgres:18-alpine`, own port, **never** `mko-bazuna-test`. `migrate --run-syncdb` + `setup_search_triggers`, then time `ListingsQuery.build_queryset(params).count()` for N ∈ {0,10,20,40,60} |
| 2 | The kill is a cgroup OOM of the backend; recovery is WAL-redo-bound | **Not re-measured** | Same private container. Confirm `client backend (PID …) was terminated by signal 9: Killed` in the PG log (note: PG 18 wording, **not** `server process` — `VAL-002` #6) plus cgroup `memory.events`; then time `time_to_kill` vs `recovery_window` and read `redo done … elapsed:` |
| 3 | `rollup_daily_metrics` ≈ 120 000 statements / 305 s | **Structure confirmed; the number is not portable** | `--dry-run` against a **production-sized** dataset on a private instance; never the shared test DB. §3 BLOCK 8 |
| 4 | `send_alerts`: 40 searches → 7.6 s, 1 000 → ~190 s | Linear and bounded; `SCHEDULER_COMMAND_TIMEOUT = 1 800 s` is the comparison bound | Same discipline as #3, against a seeded `SavedSearch` set |
| 5 | **`PERF-006`: "warm search = 510 ms"** | **NOT REPRODUCIBLE — must not be quoted.** One sample, `DEBUG=1`, a synthetic 60 000-row set, a term chosen to match 14 194 rows | Re-measure only on a private instance with **nginx + Redis** in front, a real term-frequency distribution, and the real `WEB_CPUS`/`DB_MEM_LIMIT` allocation |
| 6 | `PERF-008`: 5 015 cities → 2.9 MB page, 61 ms | **Refuted as a shipped cost** — the runtime city list is **15** rows | Re-measure only if the city-data decision lands |
| 7 | `PERF-009`: 12–13 `get_children.exists()` per page | Consistent with 7 roots × 2 sites; needs a multi-level fixture `conftest.py` does not provide | Read the captured queries of a search request against the **dev** stack (7 active roots, 205 categories). **Phase 13 must not add a fixture to `conftest.py`** |
| 8 | `PERF-010`: ≈ 35 KB statement, 1 000 `CASE` arms, 3 003 binds | **Hardware-independent and derivable statically — no DB needed.** **No latency figure exists; do not invent one** | Build the queryset with a 1 000-id `cached_ids` list; read `len(compiler.as_sql()[0])` and `len(params)` |
| 9 | `PERF-013`: 125 statements / 3.0 s / 120 `FOR UPDATE` batches at 60 000 ads | Not re-measured | Same private-instance discipline as #1 |
| 10 | The whole search cache-key suite is green | **This audit ran no pytest** (another agent held the shared DB) | `… -e PYTEST_OPTS="src/backend/apps/search/tests/test_search_cache.py src/backend/apps/lookups/tests src/backend/apps/categories/tests/test_submenu_swr.py src/backend/tests/test_cache_key_convention.py --tb=short" test` — **run this before BLOCK 1** |
| 11 | `SHOW statement_timeout` / `SHOW lock_timeout` = 0 | **Runtime-verified** (`0 ms` / `0 ms`, PostgreSQL 18.6). Re-check after `03-DB-004` lands | Phase 13 **measures against** the chosen value; it **does not set it** (§5.2 item 2) |
| 12 | `work_mem = 4 MB`, `max_connections = 100`, `DB_CPUS = 2.0`, `DB_MEM_LIMIT = 1g`, `WEB_CPUS = 1.5`, `WEB_MEM_LIMIT = 512m`, `SCHEDULER_CPUS = 0.5` | **Runtime-verified.** **None is overridden in any `.env.*`** | `docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml config` then `psql -c "SHOW work_mem"` — **key names only, never read a `.env.prod` value** |
| 13 | `_assert_p95` would return `0` after the report's prescribed fix | **Verified in-image at the pinned locust 2.46.6** | `uv run python -c "from locust.stats import RequestStats; s=RequestStats(); print(s.get('Total').get_response_time_percentile(0.95), s.total.num_requests)"` in the `web` image |
| 14 | The search-view query count at 60 ads (the number a post-fix `_QUERY_BOUND` must be derived from) | **Not captured** | `test_search_query_count.py` **does not print the count**. A one-off instrumented run is needed and **must not be committed** (BLOCK 5, gate Q7) |
| 15 | `PROMETHEUS_MULTIPROC_DIR` unset in the probe environment, so no alert could be validated | **Now set by phase 01** (`ENT-001` shipped) — the *probe* was unexercised, not the production path | `docker compose … config` on the prod stack; phase 12 owns the correction |

**The generalisable measurement rule, adopted from the validator's `VAL-003` and binding on this
plan: a single-request timing is a smoke measurement. It may establish "this is in the right
order of magnitude". It may not establish "this breaches a percentile SLO", and it may not be
written into a commit body as a performance claim.**

#### 0.2.4 Re-verification performed by this Planner at `ba23277`

Every load-bearing claim in this plan was re-checked against the tree, not taken from the
report. All fifteen findings' anchors were confirmed present:

| Claim | Tree at `ba23277` | Verdict |
|---|---|---|
| `PERF-001` gate half 1 | `src/benchmark/locustfile.py::_assert_p95` calls `stats.get("Total", "NONE").percentile(0.95)` | **present** — and `StatsEntry.percentile()` takes no argument in locust 2.46.6, so the hook raises `TypeError` on every run |
| `PERF-001` gate half 2 | `.github/workflows/ci.yml` `load-test` step: `ACTUAL_P95=$(… \| awk -F, 'NR>1 && $1=="Total" {print $6}')` guarded by `if [ -n "$ACTUAL_P95" ]` | **present** — inert; locust's CSV writes an aggregate row labelled `Aggregated`, so no row matches and the guard skips |
| locust pin | `pyproject.toml` `locust>=2.20.0`; `uv.lock` resolves **2.46.6** | **present** — a floating specifier, so `uv lock --upgrade` can silently re-introduce the API break |
| `PERF-001`/012a URLs | `locustfile.py` requests `/c/electronics` and `/c/electronics/phones` | **present** — and `apps/ads/urls.py` declares `category/<slug:category_slug>/`, so `/c/…` has **no route**; weight 3/9 |
| `PERF-003` | `rollup_daily_metrics.Command.handle` wraps a per-day `DailyAdMetrics.objects.update_or_create` loop in one `transaction.atomic()` + `advisory_lock(ROLLUP_DAILY_METRICS)` | **present** |
| `PERF-004` | `trust_tags.render_trust_badge` checks `isinstance(prefetched_cache, dict) and "trust_score" in prefetched_cache`; `RelatedObjectDoesNotExist` subclasses `AttributeError`, so `getattr(..., None)` swallows it and the `.get()` fallback fires | **present** |
| `PERF-005` | `send_alerts.Command._collect_alerts` calls `find_matching_ads(saved_search)` once per saved search; the daily path is inside `atomic()` + `advisory_lock(ALERT_DELIVERY_TASK)` | **present** |
| `PERF-006` | `search()` calls `_resolve_search_count(cached_ids, ads, query, params, request)`; at/over the cap it builds a **fresh FTS-filtered queryset and calls `.count()`** | **present** |
| `PERF-007` | `swr_cache._cold_miss_with_lock` takes the lock only on the cold-miss path; the stale-window path serves stale and only the winner recomputes | **present** — validator's narrowing holds |
| `PERF-008` | `context_processors.header_context` returns `"cities": list(City.objects.order_by("name"))`; `search()`'s context dict **independently sets** `"cities": City.objects.order_by("name")` | **present** — and see **C-7**: the report's own "Required Fixes #13" names a `save_search_cities` key that **does not exist anywhere in `src/`** |
| `PERF-009` | `get_children` occurs in templates at **three** sites: `components/header_catalog.html` ×2 and **`categories/partials/mega_submenu.html` ×1** | **present, and one more site than the report states** (D2, C-2) |
| `PERF-010` | `search()` cache-hit branch builds `Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(cached_ids)])` over the **whole** cached list, then `Paginator` slices afterwards | **present** |
| `PERF-011` | `docs/ops/prometheus-slo-alerts.yaml` carries three rules; the burn-rate and p95 rules select `handler="search:search"`; the header still carries the "Known limitation" multiprocess note | **present**; the note is **stale** (D4) and the file is **phase 12 BLOCK 11's** |
| `PERF-012b` | `profile_queries` has `SEED_SCALE_MIN_ROWS = 10_000`, guard at `row_count >= SEED_SCALE_MIN_ROWS` used twice, **no `_scale_dataset()`**, **no early exit**, and hard-coded `city_id=1` / `category_id__in=[1, 2, 3]` | **present** — and the guard prints a **green** line while skipping the assertion |
| `PERF-013` | `recompute_normalized_prices._process_batch` holds `select_for_update`; the command wraps its sweep in one `transaction.atomic()`; absent from `HOURLY_COMMANDS` / `DAILY_COMMANDS` | **present** — cost quantification only |
| `PERF-014` | `test_search_query_count.py` has `_QUERY_BOUND: int = 100`; its module docstring's real rationale **does** name both N+1s, state the measured 80 and prescribe "tighten toward the ~32-query base" | **present** — the report's quoted comment does not exist; the finding's *charge* (only the `images` sentence is false) stands |
| `PERF-015` | `docs/ops/profiling.md` documents two tools; `make profile` runs `scripts/profile_search.py` (cProfile), not `profile_queries`; the doc **does** correctly state the 10 k skip | **present** — claim 1 refuted, the `_build_queries()` gap and the wrong threshold axis survive |
| TTL handoff | `CACHES["default"]` in `config/settings/base.py` declares **only** `BACKEND`, `LOCATION`, `OPTIONS.CLIENT_CLASS` — **no `TIMEOUT`**, so Django's 300 s default applies to `SEARCH_CONTENT_VERSION_KEY`, while `swr_cache._store` writes entries for `ttl + stale_ttl` = **300 + 60 = 360 s** | **present** — the counter evicts 60 s before the entry it retires |

#### 0.2.5 The tripwires every block must satisfy

These are shipped tests. A block is not done when its own tests pass; it is done when these are
still green, and — where a block changes a count — that a tripwire is **strengthened**, never
weakened.

| Tripwire | What it pins | Phase-13 consequence |
|---|---|---|
| `apps/search/tests/test_search_query_count.py::TestSearchQueryCount` | `_QUERY_BOUND = 100` **and** a hard ban on a hot-path FTS `COUNT(*)` (any `SELECT COUNT(*)` whose SQL carries `search_vector_` / `to_tsvector`) | BLOCKS 5, 6 edit it **only** as an incidental rewrite in the same commit as the production change; BLOCK 5 re-derives the bound under Q7 and must **never** raise it to make a fix pass |
| `apps/search/tests/test_search_slo.py::TestSearchResponseSLORegression` | `SEARCH_SLO_MS = 2000` applied to a **single sample**; runs in its **own** CI step | BLOCK 1 must not move that step, and BLOCK 5's `mega_submenu` decision must not change the search response path's measured latency. **Describing the test honestly is `PERF-012c` and belongs in a block, not in a doc sweep** |
| `apps/ads/tests/test_ad_detail_queries.py` | `_QUERY_BOUND = 16` | Untouched by this plan; must stay green |
| `apps/ads/tests/test_listings_context.py` | inline `<= 16`, **and it includes the header** | BLOCK 5's `has_children` annotation changes the header's query inventory — this is the tripwire that detects it |
| `apps/ads/tests/test_search_triggers.py`, `test_setup_search_triggers.py` | the `ads_search_vector_update` trigger and the trigger DDL | Untouched — this is why the legacy `search_vector` removal is out of scope (§6.1, Q13) |
| duplicate `PerformanceSLO` assertions | the same SLO constants are asserted in more than one module | BLOCK 1 edits the SLO constants, if at all, in **every** location that asserts them, in one commit |
| `apps/core/tests/test_sweep_lock_structure.py::TestSweepLockOrdering` | exactly one `advisory_lock` per command, `in_atomic_block is True`, **`session is False`**, for all 13 lock-taking commands | BLOCK 8 (rollup) and BLOCK 9 (alerts) both touch lock-taking commands. **Neither may add, remove or reshape an `advisory_lock`, and neither may make one session-scoped** |
| `apps/currencies/tests/test_recompute_command.py` | `_process_batch` contains `select_for_update`; `TestRecomputeRowLockConcurrency` holds a row lock ~1 s | BLOCK 12 must not move the lock out of `_process_batch` without re-pointing the test |
| `apps/ads/tests/test_edit_views_locking.py::TestEditViewsLocking` | `select_for_update` count == 1, `prefetch_related` and `transaction.atomic` present in `ad_edit` | Untouched by this plan; must stay green |
| `backend/tests/test_compose_contract.py` | the `PROMETHEUS_MULTIPROC_DIR` + tmpfs **pair** on `web`; phase 01's assertions | BLOCK 1 edits the `load-test` job's **step**, not the compose contract; phase 01's assertions are never restated or renamed |
| `config/settings/tests/test_env_allowlist.py` | consumed ↔ `ALLOWED_ENV_VARS` parity, **in both directions** | Any block adding an env key must add it to the allowlist in the same commit. **This plan expects to add none** (§6.1) |
| `apps/lookups/tests/test_lookup_cache_swr.py`, `test_lookup_invalidation.py`, `test_cache_key_convention.py`, `backend/tests/test_cache_key_convention.py` | four cache key / version-key conventions | **BLOCK 4's TTL change must keep all four green** — they are the tripwire for the version-key lifetime |
| `apps/core/tests/test_advisory_lock_ids.py` | every `AdvisoryLockId.*` reference resolves | **Phase 13 allocates no lock id.** Next free integer is `14` |
| `apps/categories/tests/test_submenu_swr.py` | the cached `category_submenu` SWR | BLOCK 5's `mega_submenu` limb (Q6) and BLOCK 4's TTL work both touch this surface |

### 0.3 Scope statement (explicit)

**Fifteen findings are in scope. Thirteen are implemented by this plan; one is merged away; one
is split and only its permitted half is implemented.**

| Disposition | Count | IDs |
|---|---|---|
| **Implemented, unchanged in severity** | 11 | `PERF-001`, `PERF-003`, `PERF-004`, `PERF-005`, `PERF-008`, `PERF-009`, `PERF-010`, `PERF-012`, `PERF-013`, `PERF-014`, `PERF-015` |
| **Implemented behind a gate** | 2 | `PERF-011` (observability half only; gated on **Q12**) and the `SRCH-007` TTL limb (gated on **Q5**). **`PERF-006` #2 left this count on 2026-10-03 — `Q9` was answered and BLOCK 7 is now unconditional** |
| **Merged out of the phase** | 1 | `PERF-002` → `SRCH-001` (phase 08, **still unimplemented**) — §6.2 |
| **Rejected upstream, recorded, not re-litigated** | — | `PERF-006` #3 `work_mem`; `PERF-011` capacity limb (`workers`); `PERF-009`'s `prefetch_related("children")` |
| **Re-routed to a named owner** | — | the legacy `search_vector` + `IX_ads_search_gin` removal (**Q13**), the `?features=` ceiling (**Q14**), `DB-004`, `DB-008`, the `cache_hit_rate_slo` metric identity — §6.2 |

**What this plan does NOT do, in one sentence each, because these are the failures most likely
to be proposed in review as "obviously also fix this while you are there":**

- It does not make any change that alters a result, a count, an ordering, or a freshness
  contract — those are §6, and one of them (`PERF-006` #2) is a **product** decision.
- It does not add an index, a `statement_timeout`, a `lock_timeout`, a `work_mem` change, a
  gunicorn `workers` change, or a migration. **This plan ships zero migrations.**
- It does not touch `.github/workflows/ci-nightly.yml`'s existing jobs, `config/settings/**`, or
  any file in `docs/01-spec/`.
- It does not re-file, re-measure or partially remediate `SRCH-001`.
- It does not add a multi-level category fixture to `src/backend/conftest.py`, and it does not
  add any new pytest dependency.
- It does not claim a speedup it has not measured, and it does not write a single-sample timing
  into a commit body as a performance result (§0.2.3, rule 5).

**The plan's shape is fixed by the validated report's rollout analysis and re-verified here:**

```
PERF-001  the gate first        -> then everything else is detectable
PERF-012a the load test is real -> then the p95 number means something
PERF-012b the profiler is real  -> then the plans it prints are evidence
PERF-004 + PERF-009 + PERF-014  -> one change; then _QUERY_BOUND is derivable
PERF-006 #1 + PERF-010          -> one change; both reshape cached_ids
PERF-006 #2                     -> gated on a product ruling
PERF-003 + PERF-005             -> background write/read paths
PERF-011                        -> the observability gap (overlaps phase 12)
PERF-008                        -> the cheapest sweep, last
PERF-013 + PERF-015 docs        -> the cheapest documentation, last
```

### 0.4 Severity corrections

The validated report's severity movement (1 CRITICAL · 5 HIGH · 6 MEDIUM · 3 LOW → 0 CRITICAL ·
2 HIGH · 8 MEDIUM · 5 LOW) is **accepted as given** — the validator re-derived it against the
tree. This plan records only the corrections **this Planner** makes against that report, and
re-verify each. Where they disagree, **the tree wins** and the correction is marked ✔.

| # | Correction | Detail |
|---|---|---|
| **C-1** | **`PERF-001`'s prescribed fix is itself unsafe — the gate would be permanently green** | The report's Required-Fixes #1 prescribes `p95 = stats.get("Total").get_response_time_percentile(0.95)`. In the **pinned locust 2.46.6**, `RequestStats.get` resolves through `EntriesDict.__missing__`, which **fabricates an empty `StatsEntry`** for a missing key. Verified in-image: the report's exact expression returns **0**, and `0 > 500` is `False`, so the gate **never fails**. The real aggregate is `stats.total` (`RequestStats.total`). **Following the report here would replace a red gate with a silently green one** — strictly worse than today's loud `TypeError`. ✔ BLOCK 1 therefore fixes the gate **and** adds a positive control that fails when the metric is absent. Both are behind gates **Q1** and **Q2** |
| **C-2** | **`PERF-009` has a third call site the report denies exists** | The report states `get_children` appears in templates "**only**" at `header_catalog.html`. The tree has **three**: `components/header_catalog.html` (two sites) **and `categories/partials/mega_submenu.html`**. The report's denial came from a mis-pathed filename (`components/categories/partials/…`, `VAL-002` #3). ✔ Scope of the third site is **Q6** |
| **C-3** | **`PERF-011`'s `ENT-001` dependency is already discharged** | The rollout table sequences the new alert "after or with `ENT-001`". Phase 01 **shipped** `ENT-001` (`child_exit` + `PROMETHEUS_MULTIPROC_DIR` + tmpfs + `test_compose_contract.py`). ✔ The alert work is unblocked on that axis. **It is still blocked on the file, which is phase 12 BLOCK 11's** — Q12 |
| **C-4** | **The alert file's multiprocess caveat is stale** | `prometheus-slo-alerts.yaml` still documents a per-worker metrics limitation that phase 01 invalidated. ✔ **Phase 12 BLOCK 11 corrects it. Phase 13 does not re-correct it** — a second correction in a second file-state is a merge hazard, not a fix (§5.3) |
| **C-5** | **The TTL handoff is confirmed, and the block number is a trap** | The 2026-09-28 handbook rewrite placed the cache-version-key **lifetime** in **phase 13's handbook block 4** (ruled by **phase 08's handbook block 10**). **Phase 13's handbook block 10 is "Background and batch work" — a different block entirely.** A Planner looking for "phase 13 block 10" for the TTL lands on the wrong subject. ✔ The TTL is **this plan's BLOCK 4**; background and batch work is **this plan's BLOCKS 8, 9 and 12**. (The numbering coincidence between this plan's BLOCK 4 and the handbook's block 4 is **coincidence, not identity** — the two namespaces are unrelated and a commit must never cite a bare block number) |
| **C-6** | **`VAL-002`'s remediation target no longer exists** | `VAL-002` requires correcting six non-existent quotations *in* `.ai/audit/13-performance/findings.md`. That file is **deleted from the tree**. ✔ The correction is recorded in §0.4 (here) and in §0.2.4. **Phase 13 creates, restores or edits nothing under `.ai/audit/`** |
| **C-7** | **`PERF-008`'s prescribed fix names a key that does not exist** | Required-Fixes #13 says "remove the duplicate `save_search_cities` at `search.py:217`". **There is no `save_search_cities` anywhere in `src/`** (verified). The real duplicate is the **`cities`** context key, which `search()` sets independently of `context_processors.header_context`. ✔ BLOCK 11 follows the tree and targets `cities` |
| **C-8** | **`PERF-001`'s root cause is a *floating* dependency pin** | `pyproject.toml` declares `locust>=2.20.0`; `uv.lock` resolves 2.46.6. The `percentile()` signature break arrived through a lockfile bump nobody reviewed. ✔ A hook unit test is therefore **not optional** — it is the same class of guard as `test_i18n_completeness.py`, which exists precisely so a format change fails loudly. BLOCK 1 |
| **C-9** | **The `PERF-` prefix is already ambiguous in shipped source** | Six shipped locations carry `13-PERF-00N` strings with **wholly different** meanings (§0.1). ✔ The citation convention in §0.1 is **mandatory**, and the **sweep is reserved to phase 03 BLOCK 11**, which forbids other phases from touching it |

**Accepted verbatim from the validator, with no further correction:** the CRITICAL→HIGH
de-escalation of `PERF-001` (regressions are *not* silent today), the `PERF-002` merge,
`PERF-003`'s attribution correction, `PERF-006`'s de-escalation to MEDIUM and the rejection of
the SLO-breach argument, `PERF-007`'s narrowing to the cold-miss path, `PERF-009`'s call-count
arithmetic, `PERF-011`'s capacity rejection, `PERF-012`'s two mechanism corrections, and
`PERF-014`'s finding that the quoted comment **does not exist** (only the `images` sentence is
genuinely false).

### 0.5 Open technical questions — resolved here, or explicitly gated in their block

**This plan does not choose where technical uncertainty exists.** Twelve questions are carried
forward from the code context (§8) and two are added by this Planner. Each produces a labelled
**decision required before implementation** gate inside its block, with options and consequences,
or a named routing. **Silence is not an acceptable outcome for any of them.** A gated block does
not start until the answer is written down, and **the Implementor is forbidden from choosing an
option** (§1.3, §8.1).

| ID | Question | Block | Who decides | Status |
|---|---|---|---|---|
| **Q1** | What is the correct shape of the p95-gate fix, given that `stats.get("Total", …)` fabricates an empty entry? (a) `stats.total.get_response_time_percentile(0.95)` only; (b) `stats.total` **plus** a non-zero-request pre-assertion so an empty run fails loudly; (c) (b) plus explicit `WorkerRunner`/distributed handling, where `stats` arrives over RPC | **1** | Researcher (verify the stats shape) + Planner | **GATED.** Option (a) alone is what the report prescribes and is *unsafe* (C-1). Option (b) is this Planner's floor. Option (c) is only correct if a distributed runner is actually configured — **and it is not**; the shipped hook is registered on the process-level `test_stop` event and CI runs a single locust process |
| **Q2** | What does the positive control assert, and where does it live? (a) extend `testpaths` to collect `src/benchmark/tests/`; (b) place the test under `src/backend/apps/core/tests/`; (c) both a unit test of the hook's arithmetic **and** a CI-step assertion that the parsed p95 is non-empty | **1** | Planner | **GATED.** `pyproject.toml` `testpaths = ["src/backend", "src/telegram_bot"]` does **not** collect `src/benchmark/`. Editing `testpaths` touches a table nobody else edits but is a whole-suite behaviour change; option (b) hides benchmark tooling in a package that does not own it. Option (c) is the strongest and is this Planner's recommendation — **but "two parsers of one format" is the failure mode that produced this finding**, so the control must be one parser with a non-empty assertion, not a second parser |
| **Q3** | For `PERF-012a`: which URL targets, and what failure-rate threshold? (a) `/category/electronics/` and `/category/electronics/phones/` with a hard 0 % failure assertion; (b) the same URLs with a small non-zero tolerance; (c) derive the URLs from `categories.yaml` at run time | **2** | Planner | **GATED.** (c) would make the load test depend on catalogue contents and could silently stop testing a category. Five config values are currently restated as bare literals in the step and are candidates to be sourced from the same place as the app config |
| **Q4** | For `PERF-012b`: should `--min-rows` keep the **table-size** axis, or move to a **match-count** axis? | **3** | Planner + Researcher | **GATED.** FTS cost scales with **match count**, not table size; but a match-count target needs a way to guarantee N matches, which **no shipped environment can do** (the report's own 14 194-match term is synthetic). Whichever is chosen, the **skip must stop printing green** and must exit non-zero |
| **Q5** | For the cache-version-key lifetime: (a) retune `SEARCH_CACHE_TTL` / `SEARCH_CACHE_STALE_TTL` so the entry lifetime is strictly below any plausible counter lifetime; (b) state the invariant `version-key lifetime ≥ entry lifetime` in `cache-strategy.md` and leave the constants alone; (c) both — state the invariant **and** raise the entry TTLs' headroom | **4** | **Owner ruling**, escalated by Planner | **GATED, and it is a graded relationship, not a bug fix.** Two further facts make it non-trivial: (i) `CACHES["default"]` sets **no `TIMEOUT`**, so the counter evicts at Django's 300 s default while entries live 360 s; (ii) **phase 08 BLOCK 6 will make the counter durable (`timeout=None`)**, which makes the inequality *more* visible, not less. **Whether this is solvable independently of phase 08 BLOCK 6 is itself part of this gate** — if BLOCK 6 has not landed, option (a) is a fix to a condition that is about to change underneath it. **Still GATED after the 2026-10-03 Product Owner round — a technical gate, deliberately left open. The gate must be RE-READ AT IMPLEMENTATION TIME: if phase 08's BLOCK 6 durable-key contract has landed by then, `Q5` collapses to a retune under option (a) or (c); if it has not, option (a) is tuning against a state that is about to change underneath it and the answer must say so explicitly** |
| **Q6** | Is `categories/partials/mega_submenu.html`'s `child.get_children.exists()` in phase 13's scope? (a) in scope, all three sites; (b) in scope, `header_catalog.html` only, `mega_submenu` reported; (c) in scope, all three, with the `mega_submenu` site handled by a different mechanism because the fragment is cached | **5** | **Planner** (this is a scope ruling, not a technical one) | **GATED.** (b) leaves a known N+1 in place and would make `test_listings_context`'s bound depend on whether that fragment rendered. (c) is coherent — a cached fragment renders from cache and pays no per-request query, so the "N+1" there is a cache-miss cost, not a per-request cost. **The Implementor may not assume any of the three** |
| **Q7** | What is the post-`PERF-004` + `PERF-009` `_QUERY_BOUND`? | **5** | Researcher (measure) + Planner | **GATED, and the gate is "measure it".** The shipped comment prescribes "tighten toward the ~32-query base". **That number is unmeasured and this plan will not publish it.** The bound must be derived from a real instrumented run at the tripwire's own seed volume, recorded with the command in the commit body. **A number nobody has measured is a defect, not a default** |
| **Q8** | Does pushing `[:1000]` into SQL (the producer) change the query **plan** enough to affect the hot-path FTS `COUNT(*)` ban in `test_search_query_count`? | **6** | Researcher (run the tripwire) | **GATED — resolved by running the test, not by reasoning.** A bounded top-N `values_list` may or may not retain the `search_vector_` marker the ban matches on. **If the ban's matcher no longer fires, that is a tripwire regression and BLOCK 6 must repair the matcher, not the assertion's intent** |
| **Q9** | `PERF-006` #2: should the search results page display `SEARCH_CACHE_MAX_HITS + 1` ("1 001+") instead of the true total when the result set is truncated? | **7** | **Product Owner** — not the Planner, not the Implementor | **✅ RESOLVED 2026-10-03 — Product Owner, option (a), with a binding sub-rule: a truncated result set displays `<SEARCH_CACHE_MAX_HITS>+` and the true total is NEVER claimed when it cannot be computed.** Consequences: **BLOCK 7 is no longer `conditional` — the full deliverable ships, and BLOCK 6 alone is no longer the reduced scope.** The wording is a wording decision inside option (a), unchanged in shape. **A new user-visible string is required (the truncation notice's wording), so `ru` and `bs` `msgstr` must both be non-empty and `test_i18n_completeness.py` must be green.** Options (b) and (c) are declined |
| **Q10** | For `PERF-003`: is `bulk_create(update_conflicts=True, unique_fields=["ad","date"])` sufficient, or does the model/constraint state make it unsafe? | **8** | Researcher (verify constraint) + Planner | **GATED.** The validator verified `DailyAdMetrics` carries `uq_daily_ad_metrics_ad_date`. The gate exists because **`bulk_create(update_conflicts=True)` on Django 5.2 + psycopg requires an exact constraint match**, and a wrong `unique_fields` raises at runtime inside a nightly job nobody is watching. **The before/after numbers must be measured on a private instance; the report's "305 s → a few seconds" projection is not a promise this plan repeats** |
| **Q11** | For `PERF-005`: what is the grouping key, and has either phase 06 or phase 03 landed on `alert_query.py`? | **9** | Researcher (re-read) + Planner | **GATED.** Grouping by `(language, query)` changes result-set construction: the per-search structural filters and the 10-per-digest cap must be preserved **exactly**. And `alert_query.py` is a **three-way reservation** — phase 06 BLOCKS 5/7 (eligibility), phase 03 BLOCK 9 (delivery state), phase 13 **none** until it re-reads. **If either phase has landed, re-read; do not assume** |
| **Q12** | For `PERF-011`: what is the correct alert scope, and how is it sequenced against phase 12 BLOCK 11 on the same file? | **10** | **Coordinator** (sequencing) + Planner (scope) | **GATED.** The scope extension beyond `handler="search:search"` is free; the file is the constraint. Separately: `cache_hit_rate_slo` reads **Redis keyspace hits**, not application cache hits — **it is ~100 % by construction**, and phase 13 must not build anything on it. **Phase 13 does not touch the file until phase 12's block has landed** (§5.3) |
| **Q13** | *Planner-raised.* Does the legacy `search_vector` column + `IX_ads_search_gin` removal belong in this plan? | **§6.1** | **Coordinator** | **ROUTED, default is NO.** Phase 08 routed it to phase 13 as an "index-grading item". It is a **write-amplification win, not a latency win**; it needs a migration in **phase 05's number space**; it **breaks `test_search_triggers.py`** and `test_setup_search_triggers.py`; and the column is also a **phase-08 FTS surface**. **Phase 13 takes it only if the coordinator rules so, and then as a separate plan-level decision — not inside a block here** |
| **Q14** | *Planner-raised.* What is the correct `?features=` ceiling? | **§6.2** | **Owner**, via **phase 08's `Q2`** | **ROUTED — do not duplicate — but ANSWERED 2026-10-03 by the Product Owner.** The ruling is: **no hard-coded `?features=` ceiling; the ceiling is a catalogue invariant plus headroom, enforced by a guard test.** Phase 13's `PERF-002` remediation quality is therefore satisfied by phase 08's catalogue-invariant ceiling, and **phase 13 still implements nothing for `PERF-002`** and still duplicates no gate. The routing stands; only the question's answer now exists |

**Resolved in this plan, with the reasoning stated** — these are *rulings*, not open questions, so
that a block does not re-derive them:

- **The block taxonomy.** `mechanical` = no observable behaviour change, no outcome-changing
  gate. `behavioural` = changes an observable response, touches a shared contract, breaks a
  shipped test, or is gated. `structural` = introduces a contract or a source of truth.
  `conditional` = ships a reduced deliverable if its gate is declined. §2 and every block header.
- **The order principle.** The gate is fixed first so that everything after it is detectable.
  The harness is fixed next so that the measurement means something. Then the changes that
  *alter the query inventory* land together, so that the inventory is derivable exactly once.
  Then the contract-reshaping pair. Then the background paths. Then the observability gap. Then
  the cheapest sweeps, last.
- **`PERF-006` #1 and `PERF-010` are NOT merged into one block** in the sense of one edit — they
  are merged into **one commit with one test**, because both change the producer/consumer
  relationship of `cached_ids` in the same view and the second would otherwise be written against
  the first's assumption. They are kept as two named *sub-items* inside BLOCK 6 so each can be
  reviewed separately, and BLOCK 6's `acceptance_criteria` name both.
- **The TTL is a grading exercise, not a bug fix**, and it is therefore BLOCK 4 **with a gate**,
  not a mechanical retune. Stated plainly because the alternative reading — "just bump a
  constant" — is exactly the kind of unmeasured change §0.2.3 forbids.
- **This plan ships no migration, no index, and no new pytest dependency.** Every accepted
  remediation reuses a shipped primitive (§0.2.2 rule 3).

---

## 1. Environment and command contract for the implementor

**This environment is Windows 11 / PowerShell 7.** `make` requires WSL or GNU Make; use
`.\Makefile.ps1 <target>`. `head` / `tail` are unavailable in PowerShell.

### 1.1 Tests are Docker-only — `uv run pytest` on the host always fails

There is no PostgreSQL on `localhost:5432`. Every test run goes through the `test` service of
the `mko-bazuna-test` Compose project. `docker/entrypoint-test.sh` performs **no** database
setup: pytest-django provisions `test_mko_bazuna`, and the session-autouse fixture in
`src/backend/conftest.py` restores reference data under advisory lock `111`.

```powershell
# Alias, copied once per session
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'

# Start the DB if it is not already up
docker ps --filter "name=mko-bazuna-test-db-"
$dc up -d db

# Fast gate (skips the nightly `seed` suite) - the default iteration command
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test

# Targeted run
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="-k test_name" test
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/search/tests/test_search_query_count.py --tb=short" test

# Full suite (only when the change touches seeding or images)
$dc run --rm test
```

**Five caveats that will silently produce a wrong result if ignored:**

- `--env-file .env.test` is **required**; without it compose aborts on `${POSTGRES_*?}`
  interpolation. **Never** substitute the `mko-bazuna-dev` project name.
- Setting `PYTEST_OPTS` **replaces** the defaults
  (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`), so a
  targeted run loses xdist parallelism and DB reuse. `PYTEST_OPTS` is also **unquoted** in the
  entrypoint, so each token is word-split on spaces: `-k test_name` and bare paths work, quoted
  multi-token values do **not**. Never use `--override-ini=addopts=` — it strips
  `--import-mode=importlib`, which `pyproject.toml` requires.
- **Never run `uv run pytest` on the host**, and never use `--override-ini=addopts=`. Both are
  the documented ways to get a green gate that tested nothing.
- **Concurrent runs collide on the single `test_mko_bazuna` database.** If a gate goes red while
  another phase agent is running, **re-run it serially** before reporting it as a defect.
  Teardown races surface as `FATAL: database "test_mko_bazuna" does not exist` and
  `relation "..." does not exist`, not as product failures.
- **Never point a measurement at the shared test database.** Rows 1–4 and 9 of §0.2.3 all
  require a **private** `postgres:18-alpine` on its own port, built with
  `migrate --run-syncdb` + `setup_search_triggers`, and seeded to a production-like size. The
  shared test DB is a 60-ad fixture; every "seconds per thousand rows" number derived from it is
  fiction.

Prefer `.\Makefile.ps1 up | test | test-all | test-recreate | test-down` — they manage the
project name and env file for you.

### 1.2 **The load test is NOT a pytest run — it is a separate path**

**Say this out loud, because it is the single most common way a phase-13 block goes wrong:**
`locustfile.py` is under `src/benchmark/`, which is **outside `testpaths`**
(`["src/backend", "src/telegram_bot"]`). **No pytest invocation — fast gate, full suite, or
targeted — ever executes the p95 gate.** A green `.\Makefile.ps1 test` says nothing whatsoever
about `PERF-001`.

The p95 gate is exercised only by:

| Path | Command | When |
|---|---|---|
| **CI** | the `load-test` job in `.github/workflows/ci.yml` — seeds, starts gunicorn, runs locust headless, then evaluates the p95 | on every push/PR; **the only place the gate is enforced** |
| **Manual, whole suite** | `make load` | developer machine, against a running dev stack |
| **The hook in isolation** | the unit test BLOCK 1 adds (§3, Q2) — synthesises a `StatsEntry`, builds a `RequestStats`, and asserts the hook's arithmetic | **this is the only fast feedback available**, and it is why the control is mandatory |

**Consequences for BLOCK 1 and BLOCK 2, stated once:**

1. You cannot verify the p95 fix by running pytest. Verify it by the **unit test on the hook's
   arithmetic** plus, if you want an end-to-end confirmation, one manual `make load` against the
   dev stack. **Never against the shared test stack** (§0.2.3 rows 3, 4, 9).
2. CI's load-test server is **not** the deployment's gunicorn configuration. The step passes
   `--workers 2 --timeout 30` explicitly; production runs `workers = 3`, `timeout = 60`,
   `max_requests = 1000`. **Do not mix their numbers, and do not quote a CI latency as a
   production one** (D5).
3. The load test requires a **seeded** database. The `Seed >100 published ads` step is what
   makes any measurement meaningful; removing the dead task is what makes the remaining
   measurement honest. Both are in BLOCK 2.

### 1.3 Git contract — one Implementor, sequential, one commit per block

- **One Implementor at a time.** Never two. Never a background implementor.
- If a block is stopped mid-way, **resume the existing session**; do not launch a new agent.
- Each block is committed separately, explicitly staged: `git add <specific files>` — never
  `git add -A`, never `git add .`.
- Message form, matching the repo style: `"{type}({scope}): {description}"`, e.g.
  `fix(perf): read the p95 from stats.total and assert the metric is present (13 PERF-001 validated 2026-09)`,
  `perf(search): slice the CASE arms to the page and push the cap into SQL (13 PERF-006 #1 + PERF-010 validated 2026-09)`.
  **Every citation uses the §0.1 disambiguation convention** — `PERF-0NN (validated 2026-09)`
  — because a bare `13-PERF-004` is ambiguous against shipped source.
- **Never** `git reset`, `git checkout`, `git restore`, `git stash`, `--amend`, `--no-verify`, or
  any other history mutation. Never force-push.
- **Other agents are working in parallel**, and several are editing the same files. Files you
  did not change appearing in `git status` is normal. **Never** revert, stash or `git checkout`
  a file you did not write. If a file you are about to edit already has uncommitted changes from
  another agent, **stop and report it** rather than clobbering it. This is the normal case for
  `config/settings/base.py`, `config/settings/test.py`, `apps/core/enums.py`,
  `src/backend/conftest.py`, `pyproject.toml` and `.github/workflows/ci-nightly.yml`.
- **Take your own `git rev-parse --short HEAD`** before the first block. This plan is anchored at
  `ba23277`; the anchor has already drifted three times (§0.1). If the anchor has moved by a
  commit that touches anything in §5.3, **re-read before editing**.
- Do not commit unless the block's instructions say to.

### 1.4 Standing project rules (restated for every block)

- **English only** — comments, logs, docstrings, error messages, documentation.
- **No `print()`.** `logger = logging.getLogger(__name__)` with lazy `%s` formatting. This
  matters most in BLOCK 8 and BLOCK 9, which are the only blocks that add logging, and in
  BLOCK 8, which is where a before/after measurement will want to print a number.
- Stack: **Python 3.14 · Django 5.2 LTS (`>=5.2.16,<6.0`) · PostgreSQL 18 · aiogram 3.x ·
  native PostgreSQL FTS.** **Two processes, one DB:** web (gunicorn sync WSGI, HTMX MPA) and
  bot (aiogram, `django.setup()` + shared ORM). **Migrations run exactly once** before both
  start — a migration that must run in only one process is a defect. **This plan ships no
  migration.**
- **Django ORM is the persistence layer.** **Pydantic v2 only at system boundaries** (bot input,
  settings schemas, DTOs at a request edge). Business logic lives in `services/`. **This plan
  adds no DTO and no model.**
- **All schema changes via Django migrations**, including `RunSQL` for index and FTS DDL. **This
  plan ships none** — and any block that appears to need one is a signal that it has drifted into
  §6.
- **Fixed values via `StrEnum` / `Enum`** (project rule 10) — never plain strings, dicts or
  lists. In-repo precedent: `AdStatus`, `AdSort`, `AdvisoryLockId`, `LanguageLocale`.
- **i18n is part of DoD.** Wrap every user-visible string in `{% trans %}` / `{% blocktrans %}` or
  `gettext` / `gettext_lazy`; `msgstr` must be **non-empty** for `ru` and `bs` (`en` may be
  empty — the msgid is English). **This plan adds no user-visible string**, with exactly one
  possible exception: `PERF-006` #2's truncation notice, which **already exists** in
  `ad_list.html` and is already translated. **No `makemessages` regeneration.** `LOCALE_PATHS`
  is `[BASE_DIR / "backend" / "locale"]` — one catalogue serves web and bot, shared with phases
  03/05/06/07/10/11/14. **Append; never regenerate wholesale.**
- **Small, focused modules and functions. Composition over inheritance.** Follow existing
  patterns; **no new abstraction without strong justification**; no speculative redesign;
  **no scope creep**. Every remedy the report proposes that fails this test is in §6.
- **Production code is king.** If a test conflicts with the architecture or the business logic,
  **fix the test** — and say which change and why in the commit body. This plan pre-authorises
  exactly **one** such change, BLOCK 5's `_QUERY_BOUND` re-derivation, under gate **Q7**, and it
  must invoke rule 2 of §0.2.2 by name in the commit body.
- **Docs must stay in sync.** `docs/00-overview/doc-maintenance-rules.md`,
  `docs/99-agent/architecture.md`, `docs/99-agent/rules.md`, `docs/ops/profiling.md`,
  `docs/architecture/cache-strategy.md`. BLOCK 4, BLOCK 3 and BLOCK 12 are the documentation
  blocks; BLOCK 4's doc edit is constrained by phase 08's ownership of the same file (§5.3).
- **Secret handling is governed by phase 02**, not by this phase: `ALLOWED_ENV_VARS` in
  `config/settings/base.py` and `test_env_allowlist.py`. **This plan adds no env key**; if a
  block appears to need one, that is a report, not an edit. **Never read or print a value from
  `.env.prod`** — key names only.
- **Do not edit `src/backend/conftest.py`.** It is among the most contended files in the
  repository. If a block appears to need a new fixture — `PERF-009`'s measurement would — that
  is a signal to measure on the dev stack instead (§0.2.3 row 7).
- **Do not start, stop or modify any container or compose stack** except through the test
  commands in §1.1, the read-only `config` renders in §1.4, and the explicitly-named private
  measurement container of §1.1. Never `docker compose down -v`.
- **`config/settings/test.py` is under live concurrent edit** (observed during the audit, and it
  is phase 11 BLOCK 5's file). **`config/settings/base.py` is the most contended settings file
  after `conftest.py`** — claimed by phases 02, 03, 06, 08 and 09. Phase 13's settings surface
  is one `CACHES` read; **re-read immediately before editing either.**

### 1.5 Test authoring standard for every block

Tests verify **logic and component interaction**, not implementation trivia. No test asserts a
line number, a column count from introspection, a literal private name, a template-string
substring, or the mere presence of a symbol. Assert on **observable behaviour** and on the
**absence of danger**.

**The phase-specific rule — inherited from `VAL-003`.** A guard that asserts a *string* cannot
assert that a *control* is effective. That is the shared root cause of `PERF-001` (a gate whose
assertion could not fire), of `PERF-012b` (a profiler that prints green while skipping its
assertion), and of `PERF-014` (a bound widened to accommodate the defects it was meant to
catch). Every new guard in this plan is measured against it:

| Instead of | Assert |
|---|---|
| `stats.get("Total") is not None` | the hook **extracts a real p95 from a `RequestStats` with responses**, and a `RequestStats` with **no** responses **fails loudly** |
| `assert row_count >= SEED_SCALE_MIN_ROWS` was "skipped" with a green log | the command's **exit code** is non-zero when the threshold is not met, and the message says the measurement did not happen |
| `len(ctx.captured_queries) <= 100` | the bound is **derived from a recorded measurement** whose command is in the commit body, and **lowering** it is a failure the test detects |
| `"PRELOAD" in gunicorn.conf.py` | the process's `preload_app` is the value production runs, asserted from the loaded config |
| a comment in `test_search_query_count.py` | the **query inventory** the comment describes, measured |

**Good targets for this phase:**

- the p95 hook raises when a synthetic `RequestStats` has no responses, and returns the
  aggregate p95 when it does — and **both halves are demonstrated**;
- the load-test step's failure-rate assertion turns red when a request 404s;
- `profile_queries` exits non-zero below its threshold and zero above it, and the exit code is
  the assertion (not a log line);
- `render_trust_badge` issues **zero** additional queries when the relation is prefetched **and**
  when it is not, and the prefetched branch is genuinely taken when a prefetch is present;
- a rendered `header_catalog.html` issues **one** child-existence query in total, not one per
  non-leaf root — asserted by counting the captured queries, at a multi-root fixture;
- the cache-hit path's compiled SQL length and bind count scale with the **page**, not with
  `SEARCH_CACHE_MAX_HITS`;
- the version-key's eviction horizon is **strictly greater** than `SEARCH_CACHE_TTL +
  SEARCH_CACHE_STALE_TTL` — asserted against the *settings values*, not against a comment;
- the search results page renders the truncation notice **iff** the result set is truncated.

**Never use a line number as a task target.** Every target is a file plus a **semantic** anchor:
a class, a method, a module-level constant, a function call, a template block name, a CI job key,
a CI step name, a management-command flag, a model field, a settings key, a `.po` msgid.

Fixtures are canonical in `src/backend/conftest.py`: `seller` (900000001), `user` (900000002),
`category`, `city`, and
`create_test_ad(user, category, city, *, status=AdStatus.PUBLISHED, **kwargs)`. **This plan does
not add a fixture to that file.**

### 1.6 Task shape for every block

Each block's implementor task follows `.ai\tasks\templates\task_template.yaml`: semantic
`targets` with `type` / `name`, `semantic_anchors`, `changes`, `acceptance_criteria`,
`source_reference` / `source_section` / `source_blocks`, and an `extra_context` block carrying the
block's binding constraints **verbatim** — including, for every gated block, the question ID, the
options, and the sentence *"the Implementor is forbidden from choosing an option."*

Verification is **inline** for `mechanical` blocks (the Implementor runs `tests_to_run` and checks
`acceptance_criteria`); a **separate Validator task is required** for every `behavioural`,
`structural` and `conditional` block, for every block whose acceptance depends on a decision the
Implementor was told not to make, and for **all four agents** on the four high-risk blocks named
in their headers.

---

## 2. Scope decisions table (acceptance contract for execution)

`mechanical` = no observable behaviour change, no outcome-changing gate, safe to run without a
Validator. `behavioural` = changes an observable response, touches a shared contract, breaks a
shipped test, or is gated. `structural` = introduces a contract or a source of truth.
`conditional` = ships a reduced deliverable if its gate is declined.

| ID | Class | Disposition | Block | Severity | One-line reason |
|---|---|---|---|---|---|
| `PERF-001` | **structural** | **implement — gated on Q1 and Q2.** Read the aggregate from `stats.total`, delete the inert `awk` block, and add a **positive control that fails when the metric is absent** | **1** | **HIGH** | The CI p95 gate is broken in both directions today: the `awk` half matches no row and is skipped by its own `if [ -n … ]` guard, and the `_assert_p95` hook calls `StatsEntry.percentile()` with an argument it does not take in locust 2.46.6, so the step exits 2 on **every** run. ✔ **The report's prescribed fix is itself unsafe** — `stats.get("Total", …)` fabricates an empty entry and yields p95 = 0, a permanently green gate (C-1). **A working gate is the precondition for every other finding in this phase to be detectable**, and it is also the guard against the floating `locust>=2.20.0` pin (C-8) |
| `PERF-002` | — | **merged → `SRCH-001`; phase 13 implements nothing** | **§6.2** | CRITICAL (as `SRCH-001`) | Same code path, same defect, same failure mode, same fix family as a phase-08 CRITICAL that is **still unimplemented**. The plan-shape and row-count evidence and the composite-join remediation are recorded **as an addition to `SRCH-001`'s fix set**, not as phase-13 work. **Re-measuring it would file a second owner for one defect and invite the partial fix (cap without join collapse) that leaves a bounded-but-still-quadratic plan** |
| `PERF-003` | **behavioural** | **implement — gated on Q10.** Replace the per-day `update_or_create` loop with `bulk_create(update_conflicts=True, unique_fields=[...])`, preserving the advisory lock and the transaction shape | **8** | **HIGH** | ~120 000 statements inside one transaction that also holds an advisory lock for its whole duration. ✔ The unique constraint is verified present, but `update_conflicts=True` needs an **exact** constraint match and a mismatch raises at runtime **inside a nightly job nobody is watching** |
| `PERF-004` | **behavioural** | **implement, with PERF-009 and PERF-014, as one change.** Fix the prefetch detection; delete the false comment | **5** | MEDIUM | `RelatedObjectDoesNotExist` subclasses `AttributeError`, so `getattr(user, "trust_score", None)` swallows it and the `.get()` fallback fires **even on a correctly prefetched queryset** — the detection can never fire. The cost is bounded (index-backed `SELECT`s only when the row is absent) and the finding's second leg rests on a quote that does not exist, but the mechanism is exactly the `VAL-003` class this phase exists to remove |
| `PERF-005` | **behavioural** | **implement — gated on Q11.** Group the daily loop by distinct `(language, query)`; add per-search progress logging | **9** | MEDIUM | One FTS evaluation per saved search, inside a lock-held transaction. Linear and bounded against a 1 800 s command timeout — so **not** the "monopolising" failure the report claimed — but the loop is the wrong shape and the lock is held for its whole duration. **`alert_query.py` is a three-way reservation (phases 06, 03, 13); re-read before editing** |
| `PERF-006` | **behavioural** (was `conditional`) | **implement #1 unconditionally, as one change with `PERF-010`; #2 is now ALSO unconditional** — `Q9` was **answered 2026-10-03** by the Product Owner (option (a): display `<SEARCH_CACHE_MAX_HITS>+`, never a true total that cannot be computed) | **6** (#1), **7** (#2) | MEDIUM | At/over the cap the view builds a **fresh** FTS-filtered queryset and runs `COUNT(*)` on it, so every page view of a large result set pays a second full FTS evaluation. ✔ **Fix #3 (`work_mem`) is rejected** — a per-connection × per-node multiplier against a 1 GB `DB_MEM_LIMIT` that ships to production, and unnecessary once #1 lands. **Fix #2 was a product decision, not an engineering one, and it is now made — so the block that carries it ships its full deliverable and BLOCK 7 is no longer `conditional`** |
| `PERF-007` | **mechanical** | **implement as a documented-ruling change, or leave alone** — the decision is BLOCK 7's ruling (made 2026-10-03) or an explicit de-scoping | **§6.1** | LOW | The single-flight lock covers the **cold-miss** path only; on the stale-window path — the common case — losers correctly serve stale and only the winner recomputes. The report's "it is not a stampede guard" is **false there**. The `default`-and-fall-back contract is documented and intentional. **A task queue for cold-miss coalescing is overengineering against a 3-worker sync deployment** and is rejected |
| `PERF-008` | **mechanical** | **implement the positive-ROI limb only** — remove the **duplicate** `cities` key from `search()`'s context | **11** | MEDIUM | The design property is real at three sites, but the shipped city list is **15** rows (~8 KB, ~0.2 ms) and every reported figure came from 5 015 injected rows. Only the **duplicate** costs anything today, because it re-runs a query the context processor already ran. ✔ **The report's prescribed target `save_search_cities` does not exist** — the real key is `cities` (C-7). **Caching the header list is de-scoped**: the city-data source is a phase-06/07 question |
| `PERF-009` | **behavioural** | **implement all three call sites, with PERF-004 and PERF-014, as one change — gated on Q6 for the third** | **5** | MEDIUM | One indexed `SELECT 1 … LIMIT 1` per non-leaf root per site. ✔ **The report's recommended `prefetch_related("children")` is a no-op** against `mptt`'s `get_children`; the correct instrument is an `Exists` annotation. ✔ **The report says there are two call sites; the tree has three** (C-2) |
| `PERF-010` | **behavioural** | **implement, as one change with `PERF-006` #1** | **6** | MEDIUM | The cache-hit branch restores rank with a positional `Case`/`When` over the **whole** cached id list, so statement size and bind count scale with `SEARCH_CACHE_MAX_HITS` (1 000), not with page size. Hardware-independent and derivable statically — **no latency figure exists, and none will be invented** |
| `PERF-011` | **conditional** | **implement the observability half only — gated on Q12.** Extend the latency SLO rules beyond `handler="search:search"`. **The capacity half is rejected** | **10** | MEDIUM (observability only) | The alert-scope gap is real and cheap. ✔ **The capacity half is rejected**: `web` ships `cpus: ${WEB_CPUS:-1.5}`, and no `.env.*` overrides it, so "a worker count near the core count" means 1–2 — **fewer** than today's 3, on a 74 %-CPU workload. ✔ **`ENT-001` has shipped (C-3)**, and the file's multiprocess caveat is **stale** — but the file is **phase 12 BLOCK 11's** |
| `PERF-012` | **behavioural** | **implement in three parts: 12a → BLOCK 2, 12b → BLOCK 3, 12c → BLOCK 2** | **2**, **3** | MEDIUM | ✔ `/c/electronics` has **no route** (`apps/ads/urls.py` declares `category/<slug:category_slug>/`) and carries weight 3/9 — **33 % of the load is measuring a 404**. ✔ `profile_queries` prints a **green** line while skipping its assertion, has no `_scale_dataset()`, does not exit early, and hard-codes `city_id=1` / `category_id__in=[1, 2, 3]`. ✔ `test_search_slo.py` is a p99 constant applied to a **single sample**, and is not a percentile measurement |
| `PERF-013` | **mechanical** | **implement as cost quantification only**, with the doc corrections in BLOCK 12 | **12** | LOW | 125 statements / 3.0 s / 120 `FOR UPDATE` batches at 60 000 ads, on a command that is **absent from both `HOURLY_COMMANDS` and `DAILY_COMMANDS`** and runs only on demand. ✔ Correctly scoped as cost quantification for `DB-008`, which is **phase 03's** — **phase 13 does not change the transaction shape** |
| `PERF-014` | **behavioural** | **implement with PERF-004 and PERF-009**; the `_QUERY_BOUND` re-derivation is gated on **Q7** | **5** | LOW | The comment the finding quotes **does not exist**; the real one names both N+1s, states the measured value, and prescribes a tightening — a transparent TODO, not a rationalisation. **Only the `images` sentence is genuinely false.** ✔ **The `~32-query base` in that comment is unmeasured and this plan will not publish it** |
| `PERF-015` | **mechanical** | **implement the surviving parts** — the `_build_queries()` gap, the threshold axis, the false `make up` claim, the "best signal" wording | **3** (tool), **12** (docs) | LOW | ✔ Claim 1 is **refuted**: `make profile` runs `scripts/profile_search.py` (cProfile), not `profile_queries`, and the doc correctly states the 10 k skip. What survives is real: `_build_queries()` omits the production-path shapes, and the threshold is a **table-size** axis while FTS cost scales with **match count** |
| `VAL-001` | — | **not a code change here** — cross-phase corroboration that makes `03-DB-004` a co-equal P0 | **§6.2** | informational | The crash-recovery window is WAL-redo-bound, so the outage is *time-to-kill + redo*, the second term unbounded by the application. It changes no severity; it changes a **priority**, and it is **phase 03's** to act on. **Neither the 30 s nor the >200 s figure may be quoted as "the outage lasts N seconds"** |
| `VAL-002` | — | **not a code change here** — the target file is deleted; the correction is recorded in §0.4 | **§0.4** | HIGH for the report as a repair source | Six quoted artefacts do not exist. The *findings* stand on independent evidence; the *citations* must not be trusted as repair instructions. **Phase 13 creates, restores or edits nothing under `.ai/audit/`** (C-6) |
| `VAL-003` | **mechanical** | **implement as a convention** — enforced by §1.5 and by every block's `acceptance_criteria`. Ships no file | all | informational | A single-request timing is a smoke measurement: it may establish order of magnitude, never a percentile-SLO breach. **Two findings in the source report already turned on it** — including one that justified a HIGH severity |
| `VAL-004` | — | **rolled into the block order** — the four coupled changes and the one ordering constraint are BLOCKS 1 → 2, 5 (one change), 6 (one change), 10 | **§4.2** | MEDIUM (procedural) | ✔ The gate must land first, or the rest of the phase is unobservable. ✔ The three N+1-bound findings are one change, or `_QUERY_BOUND` publishes a number nobody measured. ✔ The two `cached_ids` findings are one change, or the second is written against the first's assumption |
| **Q1 … Q14** | — | **GATED** (Q1–Q8, Q10–Q12, each inside its block, with options and consequences written down) or **ROUTED** (Q13, Q14) | **1–12**, **§6** | — | Fourteen questions. **Nine are Planner/Researcher rulings** (Q1, Q2, Q3, Q4, Q6, Q7, Q8, Q10, Q11) · **three are owner or coordinator decisions** (Q5, Q9, Q12) · **two are routed with a stated default** (Q13 → §6.1, no; Q14 → phase 08's `Q2`). **Updated 2026-10-03: `Q9` is RESOLVED by the Product Owner (option (a)) and BLOCK 7 is no longer `conditional`; `Q14` is ROUTED *and* answered (phase 08's catalogue-invariant ceiling). Every other question is untouched** |

**Note on `PERF-007`.** It is **not** implemented as a code change, and that is a decision rather
than an oversight. The lock's cold-miss-only scope is real, but the report's own framing is
**refuted on the stale path**, the exposure is bounded by a 3-worker sync deployment, and the
"fix" the report implies (a task queue or an async coalescer) is exactly the overengineering
§0.2.2 rule 3 forbids. **The contract is documented and intentional; BLOCK 7's ruling and §6.1's
ruling are where the decision is recorded.** `Q9` was **answered** on 2026-10-03, so this
documented, measured, unchanged behaviour is now `PERF-007`'s permanent disposition rather than
the consolation left by a decline.

**Note on `PERF-006` and `PERF-010`.** They are two findings and **one commit**. The report and
`VAL-004` both require it, and the reason is structural: both change the producer/consumer
relationship of `cached_ids` in the same view. Merging them into one *block* while keeping two
named *sub-items* is deliberate — it delivers the single review window the report asked for,
while leaving each sub-item independently checkable.

**Block classification summary:** `mechanical` = **3, 11, 12** ·
`behavioural` = **2, 5, 6, 7, 8, 9, 10** · `structural` = **1** ·
`conditional` = **none** — **BLOCK 7 was `conditional` on `Q9` and is `behavioural` as of the
2026-10-03 Product Owner ruling.** (`PERF-011`'s observability half remains gated on `Q12`, which
the 2026-10-03 round did not reach; BLOCK 10 keeps its recorded reduced scope.)

---

## 3. Execution blocks

Twelve blocks. **One Implementor, strictly sequential, one commit per block** (§1.3). The
numbering *is* the serial order, and the order answers one question: **what must be true before
the next change can be trusted?**

```
src/benchmark/locustfile.py         1 only            (the gate; nothing else is detectable first)
.github/workflows/ci.yml            1, 2              (load-test job only, in place, twice)
apps/search/views/search.py         6, 7             (one commit, then the unconditional display change)
test_search_query_count.py          5 only            (with the changes it describes)
apps/search/tests/test_search_slo.py  2 only          (the honest description, incidental rewrite)
apps/core/context_processors.py     5                (the annotation's home)
templates/                          5 only            (three sites, one change)
apps/search/services/cache.py       4                (the TTL relationship)
docs/architecture/cache-strategy.md 4, after phase 08
profile_queries.py                  3                (the instrument, before it is trusted)
management commands                 8, 9, 12         (background paths, last)
docs/ops/profiling.md               12 only           (documentation, last)
```

**Nine blocks carry a labelled `decision required before implementation` gate or an external
gate** (was ten: BLOCK 7's gate was closed by the 2026-10-03 Product Owner ruling, so BLOCK 7 now
ships unconditionally). A gated block does not start until the answer is written down; **the
Implementor is forbidden from choosing an option** (§1.3, §8.1).

**The measurement contract, stated once and binding on every block.** No block ships with
"feels faster". Every block states, in its `acceptance_criteria`, **which of the two proofs it
uses**:

- **(M) measured before/after** — the exact command, the environment it ran in, and the two
  numbers, in the commit body. Applies to BLOCKS 8, 9, 12 and to BLOCK 6's *static* shape
  measurement (which needs no database).
- **(T) tripwire** — a shipped or new test that **fails when the regression returns**, and
  whose failure was **demonstrated** before the commit. Applies to BLOCKS 1, 2, 3, 4, 5, 6, 7,
  10, 11.
- **(M+T)** — both. BLOCK 5 and BLOCK 6 carry both, because they change a query inventory that a
  number and a test both describe.

**A number that cannot be produced by a command in this environment is not a result.** Where the
report's number required a private, production-sized instance and this plan does not have one,
the block ships the **tripwire** and records the number as **not measured** — never as an
estimate.

---

### BLOCK 1 — Make the p95 gate real, and make it able to fail (`PERF-001`)

| | |
|---|---|
| **Findings owned** | `PERF-001` (HIGH) · `PERF-012c` (the SLO test's honest description, incidental) |
| **Class** | **structural** — the gate is a control, and a control is a contract |
| **Depends on** | nothing in-plan. **It must be first**, because every other finding in this phase is a regression a working gate would have to catch |
| **Blocks** | BLOCK 2 (the p95 number is meaningless until this lands), and the re-baseline of BLOCK 3 |
| **Priority** | **P0.** Highest in the phase by dependency, not by blast radius |
| **Risk level** | **HIGH.** A gate fix that is *wrong in the safe direction* converts a loud red step into a permanently green one — the worst possible outcome of a performance-hygiene block |
| **Blast radius** | `.github/workflows/ci.yml`'s `load-test` job. It is **not** run by pytest (§1.2), so nothing else in the fast gate notices a regression here |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**Why this block exists at all — the defect, in full.** The `load-test` job evaluates the p95 in
**two** places and **neither can fail**:

1. **The Python hook** — `locustfile.py::_assert_p95` calls
   `stats.get("Total", "NONE").percentile(0.95)`. In locust 2.46.6 `StatsEntry.percentile()`
   takes **no** argument, so this raises `TypeError` on every run and the step exits 2.
2. **The shell half** — `ACTUAL_P95=$(cat /tmp/locust-results_stats.csv | awk -F, 'NR>1 && $1=="Total" {print $6}' | head -1)`,
   then `if [ -n "$ACTUAL_P95" ] && [ … ]`. Locust's CSV writes the aggregate row labelled
   **`Aggregated`**, not `Total`, so no row matches, `ACTUAL_P95` is empty, and the guard's own
   `-n` test **skips the comparison entirely**.

So the job is red on a `TypeError` and would be green on a 10-second response time. That is
"broken in both directions", which is why the validator de-escalated the report's CRITICAL to
HIGH (regressions are not *silent* — but they are not *caught* either).

**The correction that makes this block a gate rather than a rollback (C-1).** The report's
Required-Fixes #1 prescribes
`stats.get("Total").get_response_time_percentile(0.95)`. **That is worse than today's code.**
`RequestStats` is an `EntriesDict`; `dict.__getitem__` on a missing key routes through
`__missing__`, which **fabricates an empty `StatsEntry`**. Verified in-image at the pinned
locust 2.46.6: the report's exact expression returns **0**, `0 > 500` is `False`, and the gate
**passes forever**. The real aggregate is `stats.total` (`RequestStats.total`), which is always
present. **This is the single most important line in this plan.**

**File surface (semantic units)**

| File | Symbol | Current | Notes |
|---|---|---|---|
| `src/benchmark/locustfile.py` | `_assert_p95` | `stats.get("Total", "NONE").percentile(0.95)` | The Python half. The `P95_SLO_MS` import and the `environment.process_exit_code = 1` path stay |
| `.github/workflows/ci.yml` | job `load-test`, step "Run Locust load test" | the inert `awk` block plus five restated config literals | **BLOCK 2 also writes this step** (Q3). Sequentially, one commit apart |
| `src/backend/apps/search/tests/test_search_slo.py` | `TestSearchResponseSLORegression` module docstring | describes a single-sample p99 constant as a latency guard | **Incidental rewrite only, in this commit**, per the phase-10/11 convention. No assertion changes |

**Alternatives for the gate shape, with trade-offs — this is Q1, and it is not the Planner's to
close unilaterally:**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| (a) | `stats.total.get_response_time_percentile(0.95)` only | Minimal diff; matches the report | Poor — nothing detects an empty run | ✔ matches the report's *intent* | **Unsafe**: an empty or mis-parsed run reports 0 and passes (C-1) |
| (b) | (a) **plus** an explicit precondition: if `stats.total.num_requests == 0`, raise — the gate then fails on "no data" rather than on "fast" | One extra branch; the control is explicit and greppable | **Good** — a new locust version that empties `total` fails loudly, which is the `locust>=2.20.0` drift case (C-8) | ✔ small, local, no abstraction | The only risk is a **false red** on a legitimately empty run — which is correct behaviour for a gate, and is Q2's subject |
| (c) | (b) **plus** explicit `WorkerRunner` / distributed-runner handling, where `stats` arrives over RPC | Handles a runner shape CI does not use | Over-engineered today | ✘ speculative — the shipped hook registers on the process-level `test_stop` event and CI runs a single locust process | Adds a branch for a configuration that does not exist. **Not justified under §0.2.2 rule 3 unless Q1's Research probe finds a distributed runner in use** |

**The Implementor's alternatives, and where this block must stop:**

- **Where does the control live (Q2)?** `pyproject.toml` sets
  `testpaths = ["src/backend", "src/telegram_bot"]`, so `src/benchmark/tests/` is **not
  collected**. Option (a) extends `testpaths` — a whole-suite behaviour change in a table nobody
  else edits, and the only phase to touch it. Option (b) places the test under
  `src/backend/apps/core/tests/` — no config change, but it puts benchmark tooling in a package
  that does not own it. Option (c) does (a) **and** adds a CI-step assertion that the parsed p95
  is non-empty. **This Planner's recommendation is (c)**, on the condition that the CI assertion
  is a **non-empty check on one parser**, not a second parser — *"two parsers of one format"* is
  the failure mode that produced this finding. **The Implementor may not choose.** Q2 is a
  Planner gate.
- **What the control must assert, whatever its home.** It must be demonstrated failing **twice**:
  once with a `RequestStats` carrying responses (extracts a real, non-zero p95) and once with an
  empty one (**fails loudly**). A test that only exercises the happy path reproduces `PERF-001`
  in the guard that exists to close it.

**Binding constraints**

1. **`stats.total`, not `stats.get("Total", …)`.** Any expression that can resolve through
   `EntriesDict.__missing__` is **forbidden** in this hook, and a test must exist that fails if
   one is reintroduced.
2. **Delete the dead `awk` block**, do not repair it. It matches no row of locust's CSV and its
   own `-n` guard hides that. **Repairing it would create the "two parsers of one format" trap
   the finding is about.** If a second gate is wanted, it is a **non-empty assertion on one
   parser** (Q2 option (c)), which is a different thing.
3. **Do not move the SLO constant.** `P95_SLO_MS` stays where it is; the duplicate
   `PerformanceSLO` assertions in other modules stay in sync or are not touched. If the constant
   changes, **every** module that asserts it changes in the same commit.
4. **Do not change the seed step, the gunicorn invocation, or the locust invocation.** The step
   restates five config values as literals, but `--workers 2 --timeout 30` in CI is **not**
   production (`workers = 3`, `timeout = 60`, `max_requests = 1000`) — **do not "align" them.**
   That is D5 and it is a trap.
5. **Do not append anything after `deploy-check:` in `ci.yml`.** Phase 02's
   `_deploy_check_section()` slices from that marker to EOF.
6. **`test_search_slo.py` is edited in this commit only as an incidental rewrite** describing
   what the test *is* (a 2 000 ms single-sample bound, not a percentile measurement). **No
   assertion is changed, moved or weakened**, and the 2 000 ms value and the `PYTEST_SKIP_MARKERS`
   path stay exactly as they are. Phase 10 and phase 11 both list this file as a tripwire
   (§5.2 item 3).
7. **No latency claim goes in the commit body.** The first green run after this block may
   legitimately be red on latency; that is the intended discovery, and saying so is the correct
   commit message. Do not restate the report's 510 ms, and do not quote a CI latency as a
   production one (§1.2 item 2).

**Implementor task**

```yaml
id: task_13_b01_p95_gate_real
title: "Make the p95 gate read the aggregate and fail when the metric is absent (13 PERF-001 validated 2026-09)"
priority: high
depends_on: []
source_reference: ".ai/plans/13-performance-remediation.md"
source_section: "BLOCK 1 - Make the p95 gate real, and make it able to fail"
source_blocks: ["BLOCK 1"]
description: >
  The CI load-test p95 gate cannot fail in either of its two halves. The Python hook calls
  StatsEntry.percentile() with an argument it does not take in the pinned locust 2.46.6, so the
  step exits 2 on every run; the shell half parses locust's CSV for a row labelled "Total" when
  the aggregate row is labelled "Aggregated", and its own -n guard then skips the comparison.
  Correct the hook to read the always-present RequestStats.total aggregate, delete the dead awk
  block rather than repairing it, and add a positive control that fails when the metric is absent
  so a future locust version cannot silently re-disable the gate. The prescribed fix in the
  source report is unsafe and must not be used: stats.get("Total", ...) routes through
  EntriesDict.__missing__, which fabricates an empty StatsEntry, so it returns 0 and the gate
  always passes.
goals:
  - "the hook reads the aggregate p95 from stats.total and can never resolve through EntriesDict.__missing__"
  - "the dead awk block is deleted"
  - "a positive control fails when the stats carry no responses and extracts a real p95 when they do, with both failures demonstrated"
  - "the SLO regression test is described honestly without any assertion being changed"
extra_context: |
  BINDING CONSTRAINTS
  1. stats.total is the target. Any expression that can resolve through EntriesDict.__missing__
     is forbidden, and a test must fail if one is reintroduced.
  2. Delete the awk block; do not repair it. "Two parsers of one format" is the failure mode that
     produced this finding. A non-empty assertion on ONE parser is a different thing and is Q2's
     subject.
  3. Do not move the SLO constant. If it changes, every module that asserts it changes in the
     same commit.
  4. Do not change the seed step, the gunicorn invocation, or the locust invocation. CI's
     --workers 2 --timeout 30 is NOT production (workers = 3, timeout = 60, max_requests = 1000);
     do not align them.
  5. Do not append anything after deploy-check: in ci.yml.
  6. test_search_slo.py is an incidental rewrite only. No assertion changed, moved or weakened;
     the 2000 ms value stays. Phases 10 and 11 both list it as a tripwire.
  7. No latency claim in the commit body. The first green run may be red on latency; that is the
     intended discovery.
  GATE Q1 (gate shape) and GATE Q2 (positive-control home) MUST be answered in writing before
  implementation. The Implementor is forbidden from choosing an option.
  CITATION: use "PERF-001 (validated 2026-09)". A bare 13-PERF-001 already means the SLO guard in
  three shipped locations.
  EVIDENCE for the correction: in the web image, RequestStats().get("Total").get_response_time_percentile(0.95)
  returns 0 while RequestStats().total is present. Record the exact command in the commit body.
files:
  - path: src/benchmark/locustfile.py
    targets:
      - type: function
        name: _assert_p95
    changes:
      - "Read the aggregate from stats.total; keep P95_SLO_MS, keep process_exit_code = 1, keep the RuntimeError."
  - path: .github/workflows/ci.yml
    targets:
      - type: job
        name: load-test
      - type: step
        name: Run Locust load test
    changes:
      - "Delete the inert awk/p95 shell block. In-place edit only; append nothing after deploy-check:."
  - path: src/backend/apps/search/tests/test_search_slo.py
    targets:
      - type: class
        name: TestSearchResponseSLORegression
    changes:
      - "Docstring only: describe the test as a 2000 ms single-sample bound, not a percentile measurement."
  - path: <Q2 decides: src/benchmark/tests/ or src/backend/apps/core/tests/>
    targets:
      - type: module
        name: test_p95_gate
    changes: []
changes:
  - action: add_code
    description: >
      Add the positive control per Q2's answered option. It must construct a RequestStats with
      responses and assert the hook extracts a non-zero aggregate p95, and construct an empty
      RequestStats and assert the hook fails loudly. Both halves must be demonstrated failing
      before the commit.
  - action: modify_code
    description: >
      Correct _assert_p95 to read stats.total and add the non-empty-precondition branch chosen
      under Q1.
acceptance_criteria:
  - "the hook reads stats.total; no expression in it can resolve through EntriesDict.__missing__, and a test fails if one is reintroduced"
  - "the awk block is gone from the load-test step"
  - "the control is demonstrated both ways - a populated RequestStats yields a non-zero p95, an empty one fails the gate - and both demonstrations are recorded in the commit body"
  - "no assertion in test_search_slo.py changed; only its description"
  - "PYTEST_SKIP_MARKERS=seed is unset for the SLO test in both the local and CI paths, and that file is byte-identical apart from the docstring"
  - "P95_SLO_MS is unchanged, or every module asserting it changed in the same commit"
  - "no new pytest dependency and no testpaths change unless Q2 answered (a) or (c) explicitly"
  - "the fast Docker gate is green"
  - "no latency number is quoted in the commit body"
tests_to_run:
  - src/backend/apps/search/tests/test_search_slo.py
  - src/backend/apps/search/tests/test_search_query_count.py
  - src/backend/tests/test_compose_contract.py
  - config/settings/tests/test_env_allowlist.py
```

**Note on verification.** The p95 gate is **not** a pytest artifact (§1.2). The unit test on the
hook's arithmetic is the fast proof; one manual `make load` against the **dev** stack is the
end-to-end proof. **Neither BLOCK 1 nor any later block may verify the gate by running the fast
Docker gate**, because that gate never executes `locustfile.py`.

---

### BLOCK 2 — The load test must exercise a site that exists (`PERF-012a` + `PERF-012c`)

| | |
|---|---|
| **Findings owned** | `PERF-012a` (33 % of the load is a 404), `PERF-012c` (the SLO test is a single-sample p99 constant) |
| **Class** | **behavioural** — the CI step's pass/fail semantics change |
| **Depends on** | **BLOCK 1** (hard, dependency) |
| **Blocks** | BLOCK 3's re-baseline; every "the p95 got worse" statement in the rest of the phase |
| **Priority** | **P0** |
| **Risk level** | **MEDIUM** — a small YAML edit with a *meaningful* behavioural consequence: the job may legitimately go red on latency for the first time |
| **Blast radius** | the same `load-test` step BLOCK 1 wrote |
| **Required agents** | **Researcher · Planner · Validator** (Auditor not required — the defect is confirmed and the edit is local) |

**The defect.** `BuyerJourneyUser` requests `/c/electronics` (weight **2**) and
`/c/electronics/phones` (weight **1**). `apps/ads/urls.py` declares
`path("category/<slug:category_slug>/", listings, name="listings_category")` — **there is no
`/c/` route.** `electronics` and `phones` are both real slugs in the shipped catalogue. So
**3 of 9 task weight — 33 % of the traffic — measures a 404**, and the p95 being measured is
substantially the p95 of an error page. The rest of the step compounds this: it asserts
**nothing** about the failure rate, and it restates five config values as bare literals.

**Why it must follow BLOCK 1 and not sit beside it.** Fixing the URLs changes the measured p95
**materially upward** — the current number includes 404s, which are fast. Reading a worse p95
off a *broken* gate is meaningless; reading it off a *fixed* gate is the intended discovery.
Re-baselining before the gate is real publishes a number nobody can trust.

**File surface (semantic units)**

| File | Symbol | Current | Notes |
|---|---|---|---|
| `src/benchmark/locustfile.py` | `BuyerJourneyUser.browse_category`, `.browse_subcategory` | `/c/electronics`, `/c/electronics/phones` | The two URLs. Trailing-slash and `name=` grouping stay — `name=` is what makes the CSV per-journey rows readable |
| `.github/workflows/ci.yml` | job `load-test`, step "Run Locust load test" | asserts no failure rate; five restated literals | The failure-rate assertion lands here. **BLOCK 1 already wrote this step** |
| `src/backend/apps/search/tests/test_search_slo.py` | `TestSearchResponseSLORegression` | — | Already an incidental rewrite in BLOCK 1. **BLOCK 2 adds nothing here**; `PERF-012c` is discharged in BLOCK 1 |

**Alternatives for the URL targets and the failure-rate threshold — Q3, not the Implementor's:**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| (a) | `/category/electronics/` and `/category/electronics/phones/`, plus a **hard 0 % failure** assertion | Two named journeys that map 1:1 to shipped slugs | Good — when a category is renamed the job goes red, which is *correct* | ✔ Explicit URLs; no magic | A catalogue rename takes the job red until the URL is updated. Acceptable: the job exists to measure a real journey |
| (b) | Same URLs, small non-zero tolerance | Tolerates a flapping external dependency | Poor — the load test hits only local routes, so there is nothing legitimate to tolerate | ✘ Invents tolerance for a class of failure that does not exist here | A real regression is averaged away |
| (c) | Derive the URLs from `categories.yaml` at run time | Never goes stale | **Bad** — the job would silently stop testing *category browsing* if the slug changed, i.e. it would stop testing what it exists to test | ✘ A test whose subject is decided by the data is not a test | Silent loss of coverage; the exact `VAL-003` class this phase removes |

**Binding constraints**

1. **The URLs must be real, named routes.** `category/<slug:category_slug>/` with a trailing
   slash, and the slugs must exist in the shipped catalogue. **Do not add a `/c/` alias** — that
   would be new product surface added by a performance block.
2. **A failure-rate assertion must exist and must be demonstrated failing** (a tripwire). It
   reads the locust CSV/stats, not a hard-coded number.
3. **Do not change the locust weights, the user count, the spawn rate, or the run time.** The
   scenario's traffic shape is not this finding.
4. **Do not align CI's gunicorn flags with production's** (D5). `--workers 2 --timeout 30` in CI
   is a deliberate, different configuration. Do not mix their numbers and do not quote one as
   the other.
5. **The re-baseline is recorded, not published.** The commit body states that the p95 moved and
   in which direction, and that the previous number included 404s. It does **not** assert
   whether the new number passes: BLOCK 1's gate decides that, and BLOCK 2's commit must not
   pre-empt it.
6. **Never run the load test against the shared test stack** (§1.1). Use the **dev** stack, or
   let CI do it.

**Implementor task**

```yaml
id: task_13_b02_loadtest_real_urls
title: "Point the load test at real routes and assert a zero failure rate (13 PERF-012a validated 2026-09)"
priority: high
depends_on: [task_13_b01_p95_gate_real]
source_reference: ".ai/plans/13-performance-remediation.md"
source_section: "BLOCK 2 - The load test must exercise a site that exists"
source_blocks: ["BLOCK 2"]
description: >
  The locust BuyerJourneyUser requests /c/electronics and /c/electronics/phones, but ads/urls.py
  declares category/<slug:category_slug>/ and there is no /c/ route, so 3 of 9 task weight - 33
  percent of the traffic - measures a 404 and the p95 being measured is substantially the p95 of
  an error page. Both slugs are real catalogue slugs. The CI step additionally asserts nothing
  about the failure rate. Repoint both journeys at real named routes and add a failure-rate
  assertion that fails when any request errors.
goals:
  - "both browse journeys request routes that exist and return 200"
  - "the CI step asserts a failure rate and fails the job when it is exceeded"
  - "the re-baselined p95 is recorded with its direction, and is not asserted as passing or failing"
extra_context: |
  BINDING CONSTRAINTS
  1. Real named routes only, trailing slash. Do NOT add a /c/ alias - that is new product surface
     added by a performance block.
  2. The failure-rate assertion is a tripwire: demonstrate it failing before the commit.
  3. Do not change weights, user count, spawn rate, or run time.
  4. Do not align CI's gunicorn flags with production's (--workers 2 --timeout 30 in CI is
     deliberate and different from workers = 3, timeout = 60, max_requests = 1000). Never quote
     one as the other.
  5. Record the re-baseline, do not publish a verdict. The old number included 404s.
  6. Never run the load test against the shared test stack. Dev stack or CI only.
  7. test_search_slo.py is not edited here; PERF-012c was discharged in BLOCK 1.
  GATE Q3 (URL targets and failure-rate threshold) MUST be answered in writing before
  implementation. The Implementor is forbidden from choosing an option.
  CITATION: "PERF-012a (validated 2026-09)".
files:
  - path: src/benchmark/locustfile.py
    targets:
      - type: function
        name: browse_category
      - type: function
        name: browse_subcategory
    changes:
      - "Request the real category routes; keep the name= grouping and the timeout."
  - path: .github/workflows/ci.yml
    targets:
      - type: step
        name: Run Locust load test
    changes:
      - "Add a failure-rate assertion read from the locust results, per Q3's answered threshold."
changes:
  - action: add_code
    description: >
      Add the failure-rate assertion to the load-test step. It must fail the job when any
      request in the run returns a non-2xx, and its failure must be demonstrated.
acceptance_criteria:
  - "both browse journeys return 200; the assertion was demonstrated failing with a deliberately broken URL before the commit"
  - "the failure-rate threshold is the one Q3 recorded, and it is read from the run's results rather than hard-coded"
  - "task weights, user count, spawn rate and run time are unchanged"
  - "gunicorn flags are unchanged and no CI latency is described as a production latency"
  - "the commit body records the p95 movement and its direction, and states that the previous figure included 404s, without asserting pass or fail"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/search/tests/test_search_slo.py
  - src/backend/tests/test_compose_contract.py
```

---

### BLOCK 3 — The profiler must be runnable, and must stop lying when it skips (`PERF-012b`, `PERF-015` tool half)

| | |
|---|---|
| **Findings owned** | `PERF-012b` (`profile_queries` unrunnable and off-CI), `PERF-015` tool half (`_build_queries()` omits the production-path shapes; the threshold is the wrong axis) |
| **Class** | **behavioural** — a management command's exit code and threshold become load-bearing |
| **Depends on** | BLOCK 2 (soft, ordering). The tool fix does not need the locust fix; it is placed here so the re-baseline it enables is taken from a fixed harness |
| **Blocks** | any future `EXPLAIN` claim in this repository, and BLOCK 12's documentation |
| **Priority** | **P1** |
| **Risk level** | **LOW–MEDIUM** — a management command, but it is a **diagnostic** other people will trust |
| **Blast radius** | `profile_queries` only, plus one new CI job region in `ci-nightly.yml` |
| **Required agents** | **Researcher · Planner · Validator** |

**The defect.** `apps/core/management/commands/profile_queries.py` is the repository's only
query-plan tool, and it has three properties that make it worse than absent:

1. **It never fires its assertion.** `SEED_SCALE_MIN_ROWS = 10_000`; the guard
   `row_count >= SEED_SCALE_MIN_ROWS` is evaluated at two points, and below it the command
   **prints a line that reads like success** and returns exit 0. ✔ The report's claim that a
   `_scale_dataset()` exists and "returns early" is **false** — there is no such function
   (`VAL-002` #2). The command does not exit early; it *lies*.
2. **Its query shapes are not the production shapes.** `_build_queries()` uses
   `city_id=1` and `category_id__in=[1, 2, 3]` — hard-coded ids that name rows which need not
   exist — and omits the shape that actually dominates production traffic.
3. **It is off-CI.** Nothing runs it, so none of the above was ever observed.

**Alternatives for the threshold axis — Q4, and this one has a real trap:**

| Option | Axis | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| (a) | Keep **table size** (`--min-rows`, default `SEED_SCALE_MIN_ROWS`) | Simple, honest, measurable anywhere | Weak — says nothing about FTS cost, which scales with *matches* | ✔ Matches the doc's existing statement at `profiling.md:97` | A 10 000-row table with 12 matches reports a clean plan; the expensive case is unmeasured |
| (b) | Switch to a **match-count** axis (`--min-matches N`) | Targets the axis that actually predicts cost | Good in principle | ✘ **No shipped environment can guarantee N matches.** Producing them requires injecting a term chosen to match — which is the synthetic-data fallacy §0.2.3 row 5 forbids | The operator must construct a fixture to use the tool, and the number they construct is the number they measure |
| (c) | **Both axes**, with the skip message naming which axis was unmet | Operator chooses the question | **Good** | ✔ Additive; no existing behaviour removed | Slightly more surface; a threshold pair is two numbers to document |

**Whatever Q4 decides, one thing is unconditional and is the block's real purpose: the skip path
must stop printing green.** A tool that reports a clean run it did not perform is the single most
damaging thing an operator-facing tool can do, and it is the `VAL-003` class at the tool level.

**File surface (semantic units)**

| File | Symbol | Current | Notes |
|---|---|---|---|
| `apps/core/management/commands/profile_queries.py` | `SEED_SCALE_MIN_ROWS` | 10 000, module constant | Becomes a default for a flag under Q4 |
| | `Command.add_arguments` | `--table`, `--query`, `--dry-run` | Gains `--min-rows` (and/or `--min-matches` per Q4) |
| | `Command.handle`, `Command._build_queries`, `Command._has_seq_scan` | hard-coded ids; the skip prints green | Ids resolved from real rows; the skip exits non-zero and says the measurement did not happen |
| `.github/workflows/ci-nightly.yml` | — | no `profile_queries` job | **Phase 11 BLOCK 2 is the first phase to touch this file** (§5.3). Disjoint region, **sequential with a re-read** |

**Binding constraints**

1. **The skip path exits non-zero and its message says the measurement did not happen.** No
   wording may read as a successful run. This is the tripwire: a test must fail if the exit code
   returns to 0 on the skip path.
2. **`_build_queries()` must use resolved ids, never literals.** Every id comes from a real row
   selected by a stated criterion; if the table does not contain enough rows, the command says so
   and stops — it does not fall back to `city_id=1`.
3. **The added query shapes must be the production-path shapes** this repository actually runs —
   at minimum the search view's FTS-filtered count path and the listings path with a resolved
   city and category. Name them in the commit body.
4. **The nightly job is a nightly job.** It seeds ~20 k rows; **budget it and do not put it on
   every PR.** Add it to `ci-nightly.yml` only. **Phase 11 BLOCK 2 owns that file** — re-read
   immediately before editing, and append nothing after any phase-11 marker.
5. **Do not add a pytest dependency** and do not add a fixture to `conftest.py`.
6. **Every `EXPLAIN` claim this block produces must be reproducible by the command the block
   records.** If the block cannot produce the plan on the environment it has, it records
   "not measured" and the plan excerpt stays out of the commit.

**Implementor task**

```yaml
id: task_13_b03_profile_queries_honest
title: "Make profile_queries fail when it skips and profile the real query shapes (13 PERF-012b + PERF-015 tool half, validated 2026-09)"
priority: high
depends_on: [task_13_b02_loadtest_real_urls]
source_reference: ".ai/plans/13-performance-remediation.md"
source_section: "BLOCK 3 - The profiler must be runnable, and must stop lying when it skips"
source_blocks: ["BLOCK 3"]
description: >
  profile_queries is the repository's only query-plan tool and it reports success when it did not
  measure anything. Below SEED_SCALE_MIN_ROWS it prints a line that reads like a clean run and
  exits 0; the report's claim that a _scale_dataset() returns early is false, the guard is
  row_count >= SEED_SCALE_MIN_ROWS used twice, and the command does not exit early - it lies.
  Its query shapes are also not the production shapes: city_id=1 and category_id__in=[1, 2, 3]
  are literals naming rows that need not exist, and the dominant production path is absent. Give
  the command an explicit threshold flag, make the skip path exit non-zero and say the
  measurement did not happen, resolve every id from a real row, and add the production-path
  shapes plus a nightly job.
goals:
  - "the skip path exits non-zero and its message cannot be read as success"
  - "no literal ids remain in _build_queries"
  - "the production-path query shapes are profiled"
  - "a nightly job runs the command against a seeded dataset"
extra_context: |
  BINDING CONSTRAINTS
  1. The skip path exits non-zero and says the measurement did not happen. A test must fail if
     the exit code returns to 0 on that path.
  2. Every id in _build_queries is resolved from a real row by a stated criterion. Never fall
     back to city_id=1 or category_id__in=[1, 2, 3].
  3. The added shapes are the production-path shapes: at minimum the search view's FTS count path
     and the listings path with a resolved city and category. Name them in the commit body.
  4. The CI job goes in ci-nightly.yml ONLY, never a PR workflow. Phase 11 BLOCK 2 is the first
     phase to touch that file: re-read immediately before editing and append nothing after any
     phase-11 marker. Budget the seed volume; do not put it on every PR.
  5. No new pytest dependency; no fixture added to conftest.py.
  6. Every EXPLAIN claim must be reproducible by the command recorded in the commit body. If the
     plan cannot be produced in the environment at hand, record "not measured" and omit it.
  GATE Q4 (threshold axis) MUST be answered in writing before implementation. The Implementor is
  forbidden from choosing an option.
  CITATION: "PERF-012b (validated 2026-09)" and "PERF-015 (validated 2026-09)".
files:
  - path: src/backend/apps/core/management/commands/profile_queries.py
    targets:
      - type: constant
        name: SEED_SCALE_MIN_ROWS
      - type: function
        name: add_arguments
      - type: function
        name: handle
      - type: function
        name: _build_queries
    changes:
      - "Add the Q4 threshold flag; make the skip exit non-zero; resolve ids; add the production shapes."
  - path: src/backend/apps/core/tests/test_profile_queries.py
    targets:
      - type: module
        name: test_profile_queries
    changes: []
  - path: .github/workflows/ci-nightly.yml
    targets:
      - type: job
        name: query-profile
    changes: []
changes:
  - action: add_code
    description: >
      Add a behavioural test that drives the command below its threshold and asserts a non-zero
      exit code and a message that names the unmet threshold, and again above it asserting exit 0
      and that a Seq Scan is actually detected when one is present.
acceptance_criteria:
  - "running the command below the threshold exits non-zero and the output cannot be read as a successful measurement"
  - "the command exits 0 above the threshold and detects a real Seq Scan when one is present"
  - "no literal id remains in the command; every id is resolved from a real row"
  - "the production-path shapes are present and named in the commit body"
  - "the nightly job is in ci-nightly.yml only, seeds a production-like dataset, and is budgeted"
  - "no commit body contains an EXPLAIN plan the recorded command cannot reproduce"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/core/tests/test_profile_queries.py
  - src/backend/tests/test_compose_contract.py
```

---

### BLOCK 4 — The cache-version-key lifetime: a graded relationship, not a constant to bump (`SRCH-007`'s phase-13 limb)

| | |
|---|---|
| **Findings owned** | the `SRCH-007` **TTL limb**, routed to phase 13 by the 2026-09-28 handbook rewrite (`VAL-004` handoff, C-5). **No `PERF-` number is assigned to it** — it is a phase-13 ownership item, and it must be cited that way |
| **Class** | **structural** — it establishes a relationship between two lifetimes that did not previously have one |
| **Depends on** | **phase 08 BLOCK 6** (external, hard) — see the gate below |
| **Blocks** | BLOCK 5's `mega_submenu` limb, which shares the `submenu` TTL surface |
| **Priority** | **P1**, but **only after phase 08's block has landed** |
| **Risk level** | **HIGH for a change that looks like one line.** A TTL is the easiest thing in the repository to retune and the easiest to retune wrongly; a counter that evicts early lets an old key be **re-issued byte-identically** |
| **Blast radius** | `apps/search/services/cache.py`, `apps/categories/services/cache.py`, and — **only under phase 08's ownership** — `docs/architecture/cache-strategy.md` |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**The defect, stated exactly.** `CACHES["default"]` in `config/settings/base.py` declares only
`BACKEND`, `LOCATION` and `OPTIONS.CLIENT_CLASS` — **no `TIMEOUT`**. Django's default is
**300 s**. Meanwhile `swr_cache._store` writes a search entry for
`timeout=ttl + stale_ttl` = `SEARCH_CACHE_TTL + SEARCH_CACHE_STALE_TTL` = **300 + 60 = 360 s**.
So:

> **the version counter evicts at 300 s; the entry it retires lives 360 s.**

After the counter evicts, the next `bump_search_version()` re-issues `1` (`cache.set` on a
missing key), and a key built before the eviction becomes **byte-identical again** — restoring a
version the cache had already left behind. The same inequality holds for
`categories.cache.TREE_VERSION_KEY` against `SUBMENU_CACHE_TTL + SUBMENU_CACHE_STALE_TTL`
(also 300 + 60 = 360 s).

**This is a correctness-adjacent lifetime problem wearing a performance costume.** Under §0.2.2
rule 1 it therefore does **not** ship as a bare constant change: it ships as a **stated
invariant plus a test that fails when the inequality returns**, or not at all.

**The phase-08 interaction — why this block is gated, and why the naive fix is wrong.**
Phase 08 BLOCK 6 owns the **durable-key contract**: `timeout=None` on the version key, the four
writers migrated, the fifth consumer fixed, and the same file amended. **Phase 08 BLOCK 6 has
not landed.** Once it does, the counter is durable and unbounded, and the inequality becomes
*more* visible, not less — the entry's 360 s lifetime no longer resets. **So "just retune the
entry TTL so the counter outlives it" is a fix to a condition that is about to change underneath
it.** That is precisely the part of Q5 that cannot be closed without knowing phase 08's state.

**Alternatives — Q5, an owner ruling escalated by the Planner. This block does not close it:**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| (a) | Retune `SEARCH_CACHE_TTL` / `SEARCH_CACHE_STALE_TTL` so the entry lifetime is strictly below any plausible counter lifetime | A numeric relationship with no documented reason | **Poor** — a magic pair of numbers with a comment, and it is undone the moment phase 08 makes the counter durable | ✘ Violates §0.2.2 rule 3's "no tuning without a measurement" in spirit: it trades one unmeasured constant for another | A later edit to either constant silently re-opens the window |
| (b) | State the invariant (`version-key lifetime ≥ entry lifetime`) in `cache-strategy.md` and **leave the constants alone**; add a test that asserts the inequality against the **settings values** | One stated rule, one enforcing test, zero retuning | **Good** — when phase 08 makes the counter durable the invariant keeps holding and the test keeps passing | ✔ A relationship is a contract; a constant is a coincidence | The 300 s/360 s window remains until the counter is durable — but it is now *documented and detected* rather than latent |
| (c) | **Both** — state the invariant **and** give the entry TTLs headroom, so the relationship holds under both today's and phase 08's counter | Redundant but robust | Good | ✔ Additive, no behaviour removed | Two places to keep in sync; the test is the arbiter |

**This Planner's floor for this block, whatever Q5 decides: the block ships a *stated invariant
and an enforcing test*, or it does not ship.** A block that only moves a number has not
discharged a structural finding.

**File surface (semantic units)**

| File | Symbol | Current | Notes |
|---|---|---|---|
| `apps/search/services/cache.py` | `SEARCH_CONTENT_VERSION_KEY`, `bump_search_version`, `get_search_version` | `cache.set(key, 1)` with no explicit timeout → the cache default | **Read-only reference for phase 13.** Phase 08 BLOCK 6 owns the writers |
| | `SEARCH_CACHE_TTL`, `SEARCH_CACHE_STALE_TTL`, `SEARCH_CACHE_LOCK_TTL` | 300 / 60 / 30 | The right-hand side of the inequality. **Changed only under Q5(a) or (c)** |
| `apps/categories/services/cache.py` | `TREE_VERSION_KEY`, `SUBMENU_CACHE_TTL`, `SUBMENU_CACHE_STALE_TTL` | same shape | The same relationship, second site |
| `docs/architecture/cache-strategy.md` | the "TTL tuning" table; "Scope boundaries"; Purpose front-matter | states only `lock_ttl < stale_ttl`; the front-matter already carries the **collided** `13-PERF-006` string | **Phase 08 BLOCK 6's sole owner.** Edit only after it lands, or in the same commit if the coordinator sequences them together (§5.3) |
| a guard | — | — | Asserts `version_key_lifetime > SEARCH_CACHE_TTL + SEARCH_CACHE_STALE_TTL` **against the settings values**, not against a comment. Must be demonstrably failing when the inequality is violated |

**Binding constraints**

1. **This block does not start until phase 08 BLOCK 6's state is known.** If it has landed, the
   counter is durable and the invariant is the whole job. If it has **not**, Q5's answer must say
   whether retuning is meaningful at all — because phase 08's change would immediately re-open it.
   **Report the state; do not assume it.**
2. **`cache-strategy.md` is phase 08 BLOCK 6's sole owner.** Same commit or strictly after; never
   in parallel. Do not restate or rewrite phase 08's durable-key paragraph.
3. **The test asserts against settings values, not a comment.** A test that greps the doc
   asserts that a sentence exists, not that the relationship holds — §1.5's table, row 2.
4. **`lock_ttl < stale_ttl < ttl` must keep holding.** `30 < 60 < 300` is the shipped
   `cache-strategy.md` reference and `test_lookup_cache_swr.py` /
   `test_submenu_swr.py` / `test_search_cache.py` assert the SWR behaviour behind it. The
   lock-TTL invariant is **not** this block's to change.
5. **No new cache abstraction and no new settings key.** If the invariant cannot be stated
   without a new mechanism, that is a signal to report, not to build (rule 3).
6. **This block adds no env key**, so `test_env_allowlist.py` must be untouched and green.
7. **Never bump a TTL and call it a performance win.** A longer stale window is a *fresher-read
   tolerance* decision and a *memory* cost; it is a correctness/UX decision, and if Q5 chooses
   it, that is why the owner decides.

**Implementor task**

```yaml
id: task_13_b04_version_key_lifetime
title: "State and enforce the version-key lifetime invariant against the entries it retires (13 SRCH-007 TTL limb, handbook block 4)"
priority: high
depends_on: [phase08_block06_cache_version_contract]
source_reference: ".ai/plans/13-performance-remediation.md"
source_section: "BLOCK 4 - The cache-version-key lifetime"
source_blocks: ["BLOCK 4"]
description: >
  CACHES["default"] declares no TIMEOUT, so Django's 300 s default governs the search
  content-version counter, while swr_cache stores the entry it retires for
  SEARCH_CACHE_TTL + SEARCH_CACHE_STALE_TTL = 360 s. The counter evicts 60 s before the entry,
  and the next bump re-issues 1, making a previously-retired key byte-identical again. The same
  inequality holds for the category tree version against its submenu TTLs. This is a lifetime
  relationship, not a constant to bump: phase 08 BLOCK 6 owns making the counter durable, and
  after that change the entry's lifetime no longer resets, so the relationship must be stated and
  enforced rather than tuned blind.
goals:
  - "the version-key lifetime versus entry lifetime relationship is stated in one place"
  - "a test fails when version_key_lifetime <= SEARCH_CACHE_TTL + SEARCH_CACHE_STALE_TTL, asserting against settings values"
  - "lock_ttl < stale_ttl < ttl keeps holding"
extra_context: |
  BINDING CONSTRAINTS
  1. Do not start until phase 08 BLOCK 6's landing state is established. Report it; do not assume
     it. If it has not landed, Q5's answer must say whether retuning is meaningful at all.
  2. docs/architecture/cache-strategy.md is phase 08 BLOCK 6's SOLE owner. Same commit or strictly
     after. Never rewrite phase 08's durable-key paragraph; never restate it.
  3. The test asserts against the settings values, never against a comment or a doc string.
  4. lock_ttl < stale_ttl < ttl must keep holding (shipped: 30 < 60 < 300). Not this block's to
     change.
  5. No new cache abstraction, no new settings key, no new env key. If the invariant cannot be
     stated without a new mechanism, report it.
  6. A TTL change is a correctness and UX decision, not a performance win. Do not describe it as
     one.
  GATE Q5 (relationship shape) is an OWNER ruling and MUST be answered in writing before
  implementation. The Implementor is forbidden from choosing an option.
  CITATION: this limb has no PERF- number. Cite it as "SRCH-007 TTL limb (phase 13, handbook
  block 4)". Do NOT write a bare block number - plan block numbers and handbook block numbers are
  different namespaces, and phase 13 handbook block 10 is Background and batch work, not this.
files:
  - path: src/backend/apps/search/services/cache.py
    targets:
      - type: constant
        name: SEARCH_CACHE_TTL
      - type: constant
        name: SEARCH_CACHE_STALE_TTL
      - type: constant
        name: SEARCH_CONTENT_VERSION_KEY
    changes:
      - "Only under Q5(a) or (c): the TTL pair. Add the derived lifetime as a named constant so the relationship is a symbol, not an arithmetic expression repeated in a comment."
  - path: src/backend/apps/categories/services/cache.py
    targets:
      - type: constant
        name: TREE_VERSION_KEY
    changes:
      - "Only under Q5(c): the same relationship for the submenu surface."
  - path: src/backend/apps/search/tests/test_cache_key_convention.py
    targets:
      - type: module
        name: test_cache_key_convention
    changes: []
changes:
  - action: add_code
    description: >
      Add a test asserting the version-key lifetime is strictly greater than the entry lifetime,
      computed from the settings values, for both the search and the submenu surfaces. Demonstrate
      it failing by inverting the relationship.
  - action: modify_code
    description: >
      Record the invariant where phase 08 BLOCK 6 records its durable-key contract, subject to
      constraint 2.
acceptance_criteria:
  - "the inequality is asserted from settings values, and the guard was demonstrated failing with the relationship inverted"
  - "lock_ttl < stale_ttl < ttl still holds, and test_lookup_cache_swr, test_submenu_swr and test_search_cache are green"
  - "phase 08 BLOCK 6's landing state is recorded in the commit body"
  - "no new settings key, no new env key, no new abstraction; test_env_allowlist is untouched and green"
  - "if docs/architecture/cache-strategy.md was edited, phase 08 BLOCK 6 had already landed or the coordinator sequenced them together"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/search/tests/test_search_cache.py
  - src/backend/apps/lookups/tests
  - src/backend/apps/categories/tests/test_submenu_swr.py
  - src/backend/tests/test_cache_key_convention.py
  - src/backend/apps/search/tests/test_cache_key_convention.py
  - config/settings/tests/test_env_allowlist.py
```

---

### BLOCK 5 — The three N+1 findings are **one** change, and the bound is derived from it (`PERF-004` + `PERF-009` + `PERF-014`)

| | |
|---|---|
| **Findings owned** | `PERF-004` (HIGH → MEDIUM), `PERF-009` (MEDIUM), `PERF-014` (LOW) — **one commit, one test story** |
| **Class** | **behavioural** — the header's query inventory changes, and a shipped test's bound is re-derived |
| **Depends on** | **BLOCK 4** (hard, soft edge — BLOCK 4 owns the submenu TTL surface that the `mega_submenu` limb touches) |
| **Blocks** | BLOCK 6 and BLOCK 7 (both re-measure the search view afterwards) |
| **Priority** | **P0** — the largest coherent unit of work in the phase |
| **Risk level** | **HIGH.** Three call sites, a template contract, an annotation, a re-derived constant, and a test whose value must come from a measurement |
| **Blast radius** | `context_processors.header_context` runs on **every template render** in the site. The annotation changes the query every page issues |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**Why these three are one change and not three.** `VAL-004` item 4 is explicit: fixing the
trust-badge fallback and the header `.exists()` N+1 **changes the real query inventory**; only
then is there a defensible number for `_QUERY_BOUND`, and only then is the corrected comment
accurate. **Fixing the comment first would publish a number nobody measured.** Three sub-items,
one commit, one story:

- **5a — `PERF-004`, the prefetch detection that can never fire.** `render_trust_badge` checks
  `isinstance(prefetched_cache, dict) and "trust_score" in prefetched_cache`. On a reverse
  `OneToOne`, a prefetched relation lands in the **descriptor cache**, not
  `_prefetched_objects_cache`; and `RelatedObjectDoesNotExist` subclasses `AttributeError`, so
  the `getattr(user, "trust_score", None)` on the next line **swallows it** and the
  `SellerTrustScore.objects.get(user=user)` fallback fires — a `SELECT` per card, on a path that
  already prefetches correctly. **The detection is the defect, not only the cost.**
- **5b — `PERF-009`, three N+1 sites, not two.** One indexed `SELECT 1 … LIMIT 1` per non-leaf
  root per site. ✔ The report's `prefetch_related("children")` is a **no-op** against `mptt`'s
  `get_children` — rejected. The correct instrument is an `Exists` annotation.
- **5c — `PERF-014`, the bound and its comment.** `_QUERY_BOUND = 100` was widened to absorb
  exactly these two N+1s. ✔ The comment the finding quotes **does not exist**; the real one is
  an honest TODO that names both N+1s, states the measured value, and prescribes a tightening.

**`PERF-009`'s third call site — the scope question (Q6).** ✔ Verified at `ba23277`:
`get_children` appears at `components/header_catalog.html` (twice) **and at
`categories/partials/mega_submenu.html`**. The report states the third does not exist; it does
(C-2). The three options and their consequences:

| Option | Scope | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| (a) | All three sites, one `has_children` annotation | One mechanism everywhere; the `exists()` idiom disappears from the template layer | **Good** | ✔ | The `mega_submenu` fragment is **cached** — a cache hit pays no per-request query, so the change is a cache-miss improvement, not a per-request one. Harmless, but it must be *described* accurately |
| (b) | `header_catalog.html` only; `mega_submenu` reported to the coordinator | Smallest diff | Poor — leaves a known `.exists()` idiom in the template layer, and a future reader cannot tell it was deliberate | ✘ A known N+1 left in place, undocumented, is the `VAL-003` pattern at the code level | `test_listings_context`'s 16-query bound then depends on whether that fragment rendered |
| (c) | All three, with `mega_submenu` handled by a different mechanism because the fragment is cached | Correct per-request cost model for a cached fragment | **Good**, and it is the honest description | ✔ | Two mechanisms in one block; a reader must know which is which |

**This Planner's floor, whatever Q6 decides:** the answer is **recorded in the commit body and in
`test_listings_context`'s own docstring**, so a future reader can tell a deliberate scope
boundary from an oversight. **The Implementor may not choose.**

**The `_QUERY_BOUND` gate (Q7) — and why it is a gate and not a number.** The shipped comment says
"tighten toward the ~32-query base". **That number is unmeasured and this plan will not publish
it.** The bound must come from a real instrumented run **at the tripwire's own seed volume**,
with the command recorded. `test_search_query_count.py` **does not print the count**; deriving it
needs a one-off instrumented run that **must not be committed**. The rule this block operates
under is §0.2.2 rule 2, in this exact order: **fix the defect → measure the new inventory →
re-derive the number → change the test**, in one commit's story.

**File surface (semantic units)**

| File | Symbol | Current | Notes |
|---|---|---|---|
| `apps/trust/templatetags/trust_tags.py` | `render_trust_badge` | `_prefetched_objects_cache` membership test + `.get()` fallback | Detection corrected; the false comment deleted. **The `.get()` fallback stays** for the genuinely-unprefetched path — it is not a defect there |
| `apps/core/context_processors.py` | `header_context`, `root_categories` | `list(Category.objects.root_nodes()…)` | Gains the `has_children` annotation under Q6 |
| `templates/components/header_catalog.html` | two `{% if cat.get_children.exists %}` sites | — | Becomes `{% if cat.has_children %}` |
| `templates/categories/partials/mega_submenu.html` | `{% if child.get_children.exists %}` | — | **Scope per Q6.** In a **cached** fragment |
| `apps/search/tests/test_search_query_count.py` | `_QUERY_BOUND`, its module docstring, the hot-path `COUNT(*)` ban | 100; the `images` sentence is false | Re-derived under Q7. **The `COUNT(*)` ban is never weakened** |
| `apps/ads/tests/test_listings_context.py` | the inline `<= 16` | — | **The tripwire that detects this block's effect.** It includes the header |

**Alternatives for the trust-badge fix, with trade-offs:**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| (a) | Read the descriptor cache correctly; fall back to the related lookup only when truly unprefetched | One branch, no new API | **Good** — and the fallback is still needed for callers that do not prefetch | ✔ Smallest correct change | None material; this is the floor |
| (b) | `select_related`/prefetch at every call site instead | Removes the fallback | **Poor** — pushes the obligation onto every future caller and makes the template tag fragile | ✘ The tag is a reusable component; requiring callers to prefetch is a hidden contract | A caller that forgets pays a query per card with no error |
| (c) | Cache the badge decision on the user instance | Zero queries | **Bad** — a new cache layer inside a template tag, with its own invalidation | ✘ Overengineering (rule 3) | A stale badge on a page that already spends a request |

**Binding constraints**

1. **Three findings, one commit, one story.** Do not split 5a, 5b and 5c across commits.
2. **Do not weaken the hot-path FTS `COUNT(*)` ban** in `test_search_query_count.py`. It is the
   guard for `PERF-006`, and BLOCK 6 depends on it. If the matcher needs updating, that is
   BLOCK 6's subject under **Q8**, not this block's to relax.
3. **`_QUERY_BOUND` may only go down.** The commit body records the measured count and the
   derivation command. If the measurement cannot be taken, **the bound does not change** and
   the commit says why. A raised bound is a rejection.
4. **Do not add a multi-level category fixture to `src/backend/conftest.py`.** The N+1 is
   measurable against the **dev** stack's 7 active roots; the committed tripwire asserts the
   *shape* (a constant number of child-existence queries, not a per-root count) and must be
   demonstrably failing on the pre-fix code.
5. **`mega_submenu.html` is a cached fragment.** If Q6 chooses (a) or (c), the commit body must
   describe its benefit as a **cache-miss** improvement — claiming a per-request win there would
   be a false performance claim (§0.2.3).
6. **Do not restate phase 01's `test_compose_contract.py` assertions**, and do not touch
   `apps/categories/tests/test_submenu_swr.py`'s existing assertions — only extend if Q6 makes it
   necessary.
7. **The `13-PERF-004` string in `test_search_query_count.py` is the N+1 guard, not this
   finding.** Do not renumber it. Cite this block's findings with the §0.1 convention.

**Implementor task**

```yaml
id: task_13_b05_three_n1_one_change
title: "Fix the trust-badge prefetch detection and the header child-existence N+1 as one change, then re-derive _QUERY_BOUND from the measurement (13 PERF-004 + PERF-009 + PERF-014, validated 2026-09)"
priority: high
depends_on: [task_13_b04_version_key_lifetime]
source_reference: ".ai/plans/13-performance-remediation.md"
source_section: "BLOCK 5 - The three N+1 findings are one change"
source_blocks: ["BLOCK 5"]
description: >
  Three findings are one change because fixing them changes the query inventory, and the bound
  that describes the inventory must be derived from the result rather than published before it.
  render_trust_badge tests _prefetched_objects_cache for a reverse OneToOne, which prefetches into
  the descriptor cache instead, and RelatedObjectDoesNotExist subclasses AttributeError so the
  getattr on the next line swallows it and the .get() fallback fires a SELECT per card even on a
  correctly prefetched queryset - the detection can never fire. Separately, three template
  sites - two in header_catalog.html and one in categories/partials/mega_submenu.html, which the
  source report does not acknowledge - each issue one indexed SELECT 1 LIMIT 1 per non-leaf root;
  prefetch_related("children") is a no-op against mptt and the correct instrument is an Exists
  annotation. Finally, _QUERY_BOUND = 100 was widened to absorb both N+1s and its comment
  prescribes a tightening toward a number nobody has measured.
goals:
  - "the prefetch branch is genuinely taken when a prefetch is present, and zero extra queries are issued in either case"
  - "the header issues a constant number of child-existence queries rather than one per non-leaf root"
  - "_QUERY_BOUND is re-derived from a recorded measurement and may only go down"
extra_context: |
  BINDING CONSTRAINTS
  1. Three findings, one commit, one story. Do not split them.
  2. Never weaken the hot-path FTS COUNT(*) ban in test_search_query_count.py - it guards
     PERF-006 and BLOCK 6 depends on it. Matcher changes are BLOCK 6's subject under Q8.
  3. _QUERY_BOUND may only go DOWN. Record the measured count and the derivation command in the
     commit body. If the measurement cannot be taken, the bound does not change and the commit
     says why. The "~32-query base" in the shipped comment is UNMEASURED and must not be
     published as a result.
  4. Do not add a multi-level category fixture to conftest.py. The committed tripwire asserts the
     SHAPE (a constant number of child-existence queries, not a per-root count) and must be
     demonstrated failing on the pre-fix code. Measure the real count on the dev stack.
  5. mega_submenu.html is a CACHED fragment. If Q6 covers it, describe the benefit as a
     cache-miss improvement - claiming a per-request win there is a false performance claim.
  6. Do not restate phase 01's test_compose_contract assertions; do not weaken
     test_submenu_swr.py.
  7. The 13-PERF-004 string in test_search_query_count.py is the N+1 guard, not this finding.
     Do not renumber it.
  GATES Q6 (mega_submenu scope) and Q7 (_QUERY_BOUND derivation) MUST both be answered in writing
  before implementation. The Implementor is forbidden from choosing an option. Q6's answer must
  be recorded in the commit body AND in test_listings_context's docstring so a reader can tell a
  deliberate boundary from an oversight.
  CITATION: "PERF-004 (validated 2026-09)", "PERF-009 (validated 2026-09)",
  "PERF-014 (validated 2026-09)".
files:
  - path: src/backend/apps/trust/templatetags/trust_tags.py
    targets:
      - type: function
        name: render_trust_badge
    changes:
      - "Correct the prefetch detection per Q-options-a; keep the unprefetched fallback; delete the false comment."
  - path: src/backend/apps/core/context_processors.py
    targets:
      - type: function
        name: header_context
      - type: key
        name: root_categories
    changes:
      - "Annotate root_categories with a has_children Exists, per Q6's answered scope."
  - path: src/backend/templates/components/header_catalog.html
    targets:
      - type: template_block
        name: cat.get_children.exists
    changes:
      - "Use cat.has_children."
  - path: src/backend/templates/categories/partials/mega_submenu.html
    targets:
      - type: template_block
        name: child.get_children.exists
    changes: []
  - path: src/backend/apps/search/tests/test_search_query_count.py
    targets:
      - type: constant
        name: _QUERY_BOUND
    changes:
      - "Re-derived per Q7. The hot-path COUNT(*) ban is untouched."
changes:
  - action: add_code
    description: >
      Add a tripwire that counts child-existence queries in a rendered header and asserts a
      constant rather than a per-root figure, and that asserts render_trust_badge issues zero
      additional queries both when prefetched and when not. Demonstrate both failing on the
      pre-fix code.
acceptance_criteria:
  - "the prefetch branch is genuinely exercised; the pre-fix .get() fallback no longer fires on a prefetched queryset, demonstrated"
  - "a rendered header issues a constant number of child-existence queries; the per-root count is demonstrated failing before the fix"
  - "_QUERY_BOUND equals the measured count plus the recorded headroom, is lower than or equal to its previous value, and the commit body carries the command that produced it"
  - "the hot-path FTS COUNT(*) ban is byte-identical"
  - "test_listings_context (bound 16, includes the header), test_ad_detail_queries (16) and test_search_slo are green"
  - "no fixture was added to conftest.py"
  - "if mega_submenu was in scope, its benefit is described as a cache-miss improvement"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/search/tests/test_search_query_count.py
  - src/backend/apps/ads/tests/test_listings_context.py
  - src/backend/apps/ads/tests/test_ad_detail_queries.py
  - src/backend/apps/search/tests/test_search_slo.py
  - src/backend/apps/categories/tests/test_submenu_swr.py
  - src/backend/apps/trust/tests
```

---

### BLOCK 6 — One commit, two sub-items: cap in SQL, page-scoped rank (`PERF-006` #1 + `PERF-010`)

| | |
|---|---|
| **Findings owned** | `PERF-006` #1 (the cap path re-runs the FTS filter to count), `PERF-010` (1 000 `CASE` arms / ~3 000 binds per page view) |
| **Class** | **behavioural** — the producer's SQL shape and the cache-hit branch's statement size both change |
| **Depends on** | **BLOCK 5** (hard, dependency) |
| **Blocks** | BLOCK 7 (its half builds on this contract) |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM** — the change is small and the reasoning is verifiable statically, but it touches the `cached_ids` producer/consumer contract that two findings share |
| **Blast radius** | `apps/search/views/search.py` only |
| **Required agents** | **Researcher · Planner · Validator** (Auditor not required — both findings are confirmed and the shape is statically derivable) |

**Why one commit for two findings.** Both change the producer/consumer relationship of
`cached_ids` in the same view. Landed separately, the second is written against the first's
assumption, and a reviewer cannot see the invariant that ties them. The report and `VAL-004`
item 2 both require this. They stay two named sub-items so each is independently checkable.

- **6a — `PERF-006` #1: the cap path re-runs the FTS filter to count.** `_resolve_search_count`
  takes the cheap branch when `len(cached_ids) < SEARCH_CACHE_MAX_HITS`. **At or over the cap it
  builds a `ListsingsQuery` from scratch, re-applies the FTS filtering, and runs `COUNT(*)` on
  the result** — a second full FTS evaluation on every page view of a large result set. The
  fix: the producer already has the full filtered queryset; push the cap into SQL so the
  count path has a bounded, already-filtered queryset to work from.
- **6b — `PERF-010`: rank restore scales with the cache cap, not the page.** The cache-hit branch
  builds `Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(cached_ids)])` over the **whole**
  cached list and only then hands it to `Paginator`, which slices. Statement size and bind count
  therefore scale with `SEARCH_CACHE_MAX_HITS` (1 000), not with `per_page`. The fix: slice the
  arms to the page.

**The measurement is static, free, and there is no excuse for an invented number.** Build the
queryset with a 1 000-id `cached_ids` list and read `len(compiler.as_sql()[0])` and
`len(params)` — **no database, no latency, no environment.** The report's ~35 KB / 1 000 arms /
3 003 binds are the "before". The "after" must scale with `per_page`. **If a latency figure
appears anywhere in this block's commit body, it is fabrication** (§0.2.3 row 8: "No latency
figure exists; do not invent one").

**The plan-shape gate (Q8) — resolved by running a test, not by reasoning.** Pushing `[:1000]`
into a `values_list("id", flat=True)` queryset changes the plan to a bounded top-N heapsort.
`test_search_query_count.py`'s hot-path ban detects a dedicated FTS `COUNT(*)` by matching
`SELECT COUNT(*)` **and** `search_vector_` / `to_tsvector` in the SQL. **Whether that matcher
still fires under a bounded plan is not something to reason about.** Run the tripwire.

**Alternatives for 6a:**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| (a) | Push `[:SEARCH_CACHE_MAX_HITS]` into the producer's SQL; count from the bounded queryset | One query instead of two; the producer's contract becomes explicit | **Good** | ✔ Reuses the existing producer and the existing constant | If the ban's matcher stops firing, the tripwire is inert — **Q8** |
| (b) | Cache the count alongside the IDs, in the same cache entry | Zero extra queries on a hit | **Bad** — a second value with its own invalidation, in a phase that must not add caching | ✘ New state, new invalidation path | A count that survives its result set, or vice versa |
| (c) | Raise `work_mem` so the count query is cheaper | No code change | **Poor** | ✘ **Rejected upstream.** A per-connection × per-node multiplier against a 1 GB `DB_MEM_LIMIT` that ships to production, and unnecessary once (a) lands | An immediate container OOM in place of a slow request |

**Alternatives for 6b:**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| (a) | Slice `cached_ids` to the page window **before** building the `Case`/`When` | The rank order is preserved exactly for the rows on the page | **Good** | ✔ Reuses `Paginator`'s existing window | None material; this is the floor |
| (b) | Fetch the page by `pk__in` and sort in Python | No SQL arms at all | Poor — moves ordering out of the database for a database's job | ✘ | A page ordered in Python disagrees with the queryset's own ordering under any future tiebreak |
| (c) | Keep the full `Case`/`When` and raise a statement-parameter ceiling | No code change | **Bad** | ✘ | Hides a volume-dependent statement behind a raised limit |

**Binding constraints**

1. **Two sub-items, one commit, one test story.** Do not split 6a and 6b.
2. **The rank order of the rows on the page must be byte-identical before and after.** This is
   the tripwire: a test that renders a multi-page result set at both positions and asserts the
   sequence of ad ids is unchanged. **Changing the ordering is a semantics change, not a
   performance change** (§0.2.2 rule 1).
3. **No latency number.** The before/after is the compiled statement's length and bind count.
3. **The hot-path FTS `COUNT(*)` ban may not be weakened.** If the matcher needs re-pointing, it
   is re-pointed **to the same intent** and the change is explained — under **Q8**.
5. **`results_truncated` semantics are unchanged by 6a.** 6a changes *how* the count is obtained,
   not *what is displayed*. Changing the displayed value is BLOCK 7, under the
    **Q9 ruling of 2026-10-03**.
6. **No new cache key, no new entry shape, no new settings constant.**

**Implementor task**

```yaml
id: task_13_b06_cap_in_sql_page_scoped_rank
title: "Cap the producer in SQL and scope the rank CASE arms to the page (13 PERF-006 #1 + PERF-010, validated 2026-09)"
priority: high
depends_on: [task_13_b05_three_n1_one_change]
source_reference: ".ai/plans/13-performance-remediation.md"
source_section: "BLOCK 6 - One commit, two sub-items"
source_blocks: ["BLOCK 6"]
description: >
  Two findings, one commit, because both change the producer/consumer relationship of cached_ids
  in the search view. PERF-006 #1: when the cached list reaches SEARCH_CACHE_MAX_HITS,
  _resolve_search_count rebuilds the queryset from scratch, re-applies the FTS filtering and runs
  COUNT(*) on it - a second full FTS evaluation on every page view of a large result set. Push the
  cap into the producer's SQL so the count path works from a bounded, already-filtered queryset.
  PERF-010: the cache-hit branch restores rank with a positional Case/When over the whole cached
  list before Paginator slices it, so statement size and bind count scale with the 1000-ad cap
  rather than with per_page. Slice the arms to the page window.
goals:
  - "the at/over-cap count path no longer re-runs the FTS filter"
  - "the compiled cache-hit statement's size and bind count scale with the page, not with SEARCH_CACHE_MAX_HITS"
  - "the rendered order of ads on a page is byte-identical before and after"
extra_context: |
  BINDING CONSTRAINTS
  1. Two sub-items, one commit, one test story.
  2. The rank order of the rows on the page must be byte-identical. A test renders a multi-page
     result set and asserts the ad-id sequence is unchanged. Changing ordering is a semantics
     change, not a performance change.
  3. The before/after measurement is the compiled statement's length and bind count
     (len(compiler.as_sql()[0]) and len(params)) with a 1000-id cached_ids list. NO DATABASE, NO
     LATENCY NUMBER. A latency figure in this commit body is fabrication.
  4. Never weaken the hot-path FTS COUNT(*) ban in test_search_query_count.py. If the matcher
     needs re-pointing, re-point it to the SAME INTENT and explain it.
  5. results_truncated semantics are unchanged by 6a. Changing the DISPLAYED value is BLOCK 7
     under the Q9 ruling of 2026-10-03 and must not leak in here.
  6. No new cache key, no new entry shape, no new settings constant. work_mem is REJECTED.
  GATE Q8 (does the plan change break the ban's matcher) is resolved by RUNNING
  test_search_query_count.py, not by reasoning. The result MUST be recorded in the commit body.
  CITATION: "PERF-006 #1 (validated 2026-09)" and "PERF-010 (validated 2026-09)".
files:
  - path: src/backend/apps/search/views/search.py
    targets:
      - type: function
        name: search
      - type: function
        name: _resolve_search_count
    changes:
      - "6a: the producer caps in SQL; the at/over-cap count path consumes a bounded, already-filtered queryset."
      - "6b: the cache-hit branch scopes the Case/When arms to the page window before building the rank."
  - path: src/backend/apps/search/tests/test_search_query_count.py
    targets:
      - type: function
        name: test_search_view_query_count_bounded
    changes:
      - "Matcher re-pointing only if Q8 demonstrates it is needed, and then to the same intent."
changes:
  - action: add_code
    description: >
      Add a test asserting the rendered ad-id order across multiple pages of a result larger than
      the page size is identical to the pre-change ordering, and a test asserting the compiled
      cache-hit statement's length and bind count do not grow with cached_ids.
acceptance_criteria:
  - "the at/over-cap path issues no second FTS-filtering evaluation, and the hot-path COUNT(*) ban is intact and was run"
  - "the compiled statement's length and bind count are recorded before and after, with the command; the after figure scales with per_page"
  - "the rendered order of ads across pages is byte-identical, demonstrated against the pre-change ordering"
  - "results_truncated and total_count are unchanged for every non-truncated case"
  - "no latency number appears in the commit body"
  - "no new cache key, entry shape or settings constant"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/search/tests/test_search_query_count.py
  - src/backend/apps/search/tests/test_search_cache.py
  - src/backend/apps/ads/tests/test_listings_context.py
  - src/backend/apps/search/tests/test_search_slo.py
```

---

### BLOCK 7 — The truncated-count UX (`PERF-006` #2) — **unconditional since 2026-10-03**

| | |
|---|---|
| **Findings owned** | `PERF-006` #2 — **no longer conditional** |
| **Class** | **behavioural** — it changes a rendered, user-visible number. **It was `conditional`; the 2026-10-03 Product Owner ruling on `Q9` made it unconditional and it now ships its FULL deliverable** |
| **Depends on** | **BLOCK 6** (hard, dependency). **`Q9` is RESOLVED — the external gate is closed and is no longer a dependency** |
| **Blocks** | nothing |
| **Priority** | **P2** |
| **Risk level** | **MEDIUM** (lowered from HIGH). The "owner not consulted" risk is **CLOSED**: the owner was consulted and ruled on 2026-10-03. The remaining risk is purely the wording of a number a buyer reads |
| **Blast radius** | the search results page — the highest-traffic page in the product |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**This is not a performance block and must not be allowed to become one.** `PERF-006` #2 changes
the search results page from showing the **true total match count** to showing
`SEARCH_CACHE_MAX_HITS + 1` (i.e. "1 001+") whenever the result set is truncated. Under §0.2.2
rule 1 it is **not** a performance change by any reading. It is in this plan because it is the
*other half* of a finding this plan must close completely, and because leaving it unaddressed
leaves `PERF-006` half-remediated. **That obligation is now discharged: `Q9` is answered and the
half ships.**

**GATE Q9 — ✅ RESOLVED 2026-10-03 by the Product Owner: option (a).**

> **The ruling, verbatim in effect: a truncated result set displays `<SEARCH_CACHE_MAX_HITS>+`;
> the true total is never claimed when it cannot be computed.** Options (b) (keep the true count)
> and (c) (compute an exact count by cheaper machinery) are **declined**. The binding sub-rule is
> the second clause: **this is not merely "show the cap" — it is "never assert a total you have
> not computed."** An Implementor who renders a cached, remembered or previously-computed total in
> the truncated branch has not implemented the ruling.
>
> **Block-level consequences:**
> 1. **BLOCK 7 is no longer `conditional`.** The **full** deliverable ships.
> 2. **BLOCK 6 alone is no longer the reduced scope** — that framing is withdrawn.
> 3. **A new user-visible string is required** (the truncation notice's wording under option (a)),
>    so `ru` **and** `bs` `msgstr` must both be non-empty and `test_i18n_completeness.py` green.
>    The catalogue is appended to, never regenerated.
> 4. The **"owner is not consulted and the displayed count changes by default"** risk (§7, block 7)
>    is **CLOSED**. §7's row is restated, not deleted.
> 5. The displayed value remains **exactly `SEARCH_CACHE_MAX_HITS + 1`** — the ruling changes the
>    block's *status*, not its arithmetic. A cap that produces "1 000" while the cap is 1 000 is
>    indistinguishable from the true count and fails the user's intent.

The options table below is **retained as the record of what was chosen against** — it is not a
live choice and an Implementor may not re-pick (b) or (c).

| Option | Displayed count | Maintains | Future evolution | Consequence |
|---|---|---|---|---|
| (a) — **CHOSEN, 2026-10-03** | `SEARCH_CACHE_MAX_HITS + 1`, with the existing truncation notice | Honest about the cap; a buyer sees a bounded number | Follows the cap automatically; every cap change is visible | **A buyer is told "1 001+" when 4 000 ads match.** Some will read that as "about a thousand" — which is why the ruling binds the notice wording and why the notice must be unambiguous |
| (b) — **declined** | The true count (today) | Correct information | Every page view of a large result set pays a second FTS evaluation — **the defect** | The finding stays open |
| (c) — **declined** | An exact count computed by a cheaper mechanism (an approximate-count query, a maintained counter) | Correct and cheap | **Adds state** — a counter needs invalidation, and `search` is not the only writer | New machinery for a 60-ad-seeded product's slowest path; overengineering (rule 3) unless volume justifies it |

**No reduced deliverable remains.** BLOCK 6 alone was the reduced scope when `Q9` was open; that
sentence is **withdrawn**, and a commit for BLOCK 7 that ships nothing is a defect.

**Binding constraints**

1. **`Q9` is answered (2026-10-03, Product Owner, option (a)).** The Implementor may not choose,
   and may not "decline on the owner's behalf".
2. **The truncation notice's wording is the deliverable's remaining product surface, and it is a
   new user-visible string.** `msgstr` must be **non-empty** for `ru` and `bs` and
   `test_i18n_completeness.py` must be green. **Append to the catalogue; never regenerate it
   wholesale.** No `makemessages` sweep.
3. **The rendered-page assertion is mandatory**, and it is the tripwire: the page must render
   the notice **iff** the result set is truncated, and must **not** render it otherwise.
4. **The total is `SEARCH_CACHE_MAX_HITS + 1` — exactly, not approximately — and no true total is
   ever claimed when it cannot be computed.**
5. **The analytics and the `has_results` semantics are unchanged.** `has_results` is derived
   from `total_count > 0` and a truncated result set is never empty; do not let a refactor
   quietly change that.
6. **This block may not change the cache, the producer, or the `Case`/`When` slice.** Those are
   BLOCK 6's and they have landed.

**Implementor task**

```yaml
id: task_13_b07_truncated_count_ux
title: "Implement the truncated-count display ruled on 2026-10-03: <SEARCH_CACHE_MAX_HITS>+, never a true total that cannot be computed (13 PERF-006 #2, validated 2026-09)"
priority: medium
depends_on: [task_13_b06_cap_in_sql_page_scoped_rank]
source_reference: ".ai/plans/13-performance-remediation.md"
source_section: "BLOCK 7 - The truncated-count UX"
source_blocks: ["BLOCK 7"]
description: >
  When a search result set reaches SEARCH_CACHE_MAX_HITS the view today recomputes the true total
  with a second FTS evaluation so the page can display the real match count. The Product Owner
  ruled on 2026-10-03 that a truncated result set displays <SEARCH_CACHE_MAX_HITS>+ and that the
  true total is never claimed when it cannot be computed. This block therefore ships its FULL
  deliverable unconditionally: no code change is a defect, and BLOCK 6 alone is no longer the
  reduced scope.
goals:
  - "the truncated branch shows exactly SEARCH_CACHE_MAX_HITS + 1 and never a true total it did not compute"
  - "the truncation notice renders IFF the result set is truncated, demonstrated both ways"
  - "the new user-visible wording has non-empty ru and bs msgstr"
extra_context: |
  Q9 IS RESOLVED - 2026-10-03, Product Owner, option (a). The block is UNCONDITIONAL and ships its
  full deliverable. The Implementor may not choose, and may not decline on the owner's behalf.
  The ruling's binding sub-rule is that the TRUE TOTAL IS NEVER CLAIMED WHEN IT CANNOT BE
  COMPUTED - rendering a cached, remembered or previously-computed total in the truncated branch
  is not an implementation of the ruling.
  BINDING CONSTRAINTS
  1. Q9 is answered; option (a) is the ruling. No option choice remains.
  2. The truncation notice's wording is a NEW user-visible string. ru and bs msgstr must be
     non-empty and test_i18n_completeness must be green. Append; never regenerate the catalogue.
     No makemessages sweep.
  3. The rendered-page assertion is the tripwire: notice rendered IFF truncated, both ways.
  4. The displayed value is exactly SEARCH_CACHE_MAX_HITS + 1, not approximately, and no true
     total is claimed when it cannot be computed.
  5. has_results and the analytics semantics are unchanged; a truncated result set is never empty.
  6. Do not change the cache, the producer, or the CASE slice - those are BLOCK 6's.
  THERE IS NO REDUCED DELIVERABLE. Shipping no code is a defect, not a recorded decline.
files:
  - path: src/backend/apps/search/views/search.py
    targets:
      - type: function
        name: _resolve_search_count
    changes:
      - "Return the capped value with results_truncated set; never return a total that was not computed."
  - path: src/backend/templates/ads/list.html
    targets:
      - type: template_block
        name: results_truncated
    changes:
      - "Render the truncation notice whose wording is the new user-visible string; ru and bs non-empty."
changes:
  - action: add_code
    description: >
      Return the capped value from _resolve_search_count when the result set is truncated, and never
      assert a true total that was not computed.
  - action: add_code
    description: >
      Add a rendered-page test asserting the notice appears exactly when the result set is
      truncated, and that the displayed total is exactly SEARCH_CACHE_MAX_HITS + 1 in that case
      and the true count otherwise. Demonstrate both branches.
acceptance_criteria:
  - "the Q9 answer (Product Owner, 2026-10-03, option (a)) and its accepted consequences are recorded in the commit body"
  - "the truncated total is exactly SEARCH_CACHE_MAX_HITS + 1 and no un-computed true total is ever claimed; the notice renders iff truncated, demonstrated both ways"
  - "the block shipped code - a no-code commit is a defect"
  - "ru and bs msgstr are non-empty for the new/changed string; test_i18n_completeness is green; no catalogue regeneration"
  - "has_results and analytics semantics unchanged"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/search/tests/test_search_query_count.py
  - src/backend/apps/search/tests/test_search_cache.py
  - src/backend/tests/test_i18n_completeness.py
  - src/backend/apps/ads/tests/test_listings_context.py
```

---

### BLOCK 8 — `rollup_daily_metrics`: the write loop, without touching the lock (`PERF-003`)

| | |
|---|---|
| **Findings owned** | `PERF-003` (HIGH) |
| **Class** | **behavioural** — a nightly command's write path changes shape |
| **Depends on** | BLOCK 7 (soft, ordering — no file overlap; placed here so all request-path work is finished) |
| **Blocks** | BLOCK 9 (the other background command) |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM.** The change is one call; the risk is that `bulk_create(update_conflicts=True)` raises **inside a nightly job nobody is watching** |
| **Blast radius** | one management command, run nightly |
| **Required agents** | **Researcher · Planner · Validator** |

**The defect.** `Command.handle` opens one `transaction.atomic()` and takes
`advisory_lock(AdvisoryLockId.ROLLUP_DAILY_METRICS)`, then walks the date range issuing a
`DailyAdMetrics.objects.update_or_create(...)` per ad per day — the report's measurement is
~120 000 statements in one ~305 s transaction. ✔ The validator confirmed the model carries
`uq_daily_ad_metrics_ad_date`, so the constraint the fix needs is present. ✔ The report's
*attribution* ("99.97 % pure per-statement overhead, ~2.5 ms/row") and its **"→ a few seconds"
projection are not accepted** and are not repeated here.

**Why this is a HIGH finding despite the projection being unproven.** The transaction holds an
advisory lock for its whole duration and blocks every other writer to the same rows for the same
duration. **The cost is not the 305 s; it is that the lock is held for the cost.** That is the
claim this block is built on, and it is structural rather than measured.

**Alternatives, with trade-offs — the shape matters more than the constant:**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| (a) | `bulk_create(objs, update_conflicts=True, unique_fields=[...], update_fields=[...])` | **One** statement per chunk; the unique constraint does the upsert | **Good** — the constraint is already there and is the right abstraction | ✔ Django 5.2 + psycopg, existing idiom in `send_alerts` | A wrong `unique_fields` **raises at runtime**, nightly, unnoticed. **Q10 exists for exactly this** |
| (b) | `bulk_create` with `ignore_conflicts=True` | Simple | **Poor** — silently drops the update, so a changed metric never lands | ✘ | Metrics quietly go stale, with no error. **Worse than the current defect** |
| (c) | Keep the loop; batch it with `transaction.atomic()` per chunk | Simple | **Bad** — many small transactions under one advisory lock, with more commit overhead and the same lock duration | ✘ | No material improvement and more moving parts |
| (d) | Restructure the rollup into a single `INSERT ... SELECT ... GROUP BY` | Best asymptotics | **Good**, and it removes the Python loop entirely | ✔ on principle, ✘ in **this** block | It is a different command with different semantics and its own verification burden. **Out of scope** — noted as a follow-up, not rejected on merit |

**Binding constraints**

1. **The advisory lock is untouched.** `test_sweep_lock_structure.py::TestSweepLockOrdering`
   asserts exactly one `advisory_lock` per command, `in_atomic_block is True`, **`session is
   False`**. **This block must not add, remove, reshape or session-scope that lock.** Phase 13
   allocates **no** `AdvisoryLockId` — next free integer is `14` — and
   `test_advisory_lock_ids.py` must stay green untouched.
2. **The transaction shape is preserved**: one `transaction.atomic()` around the command's
   work, taken **inside** the lock exactly as today. **Whether the whole sweep should be one
   transaction is `DB-008`, which is phase 03's** — this block does not pre-empt it.
3. **`update_conflicts=True` requires an exact constraint match.** `unique_fields` and the
   conflict target must name the real constraint; the commit body records the constraint's name
   and where it was verified. **This is Q10's gate.**
4. **`--dry-run` still writes nothing and still reports the same summary.** The dry-run path is
   what an operator runs first, and it must not be the thing that breaks.
5. **Before/after must be measured, not projected.** Run the command with `--dry-run` and with
   real writes against a **production-sized dataset on a private instance** (§1.1). **The
   report's "305 s → a few seconds" is not a promise this block makes.** If the measurement
   cannot be taken in the environment at hand, the commit says "not measured" and reports only
   the statement-count reduction, which is derivable statically from the row count.
6. **No migration.** If the fix appears to need a constraint change, **stop and report** — that
   is `DB-008`/phase 03, and this plan ships zero migrations.
7. **No `print()`.** Any progress output is `logger.info` with lazy `%s`, and it is **value-free
   of ad content**.

**Implementor task**

```yaml
id: task_13_b08_rollup_bulk_upsert
title: "Replace the per-row upsert loop with a chunked bulk_create update_conflicts upsert (13 PERF-003, validated 2026-09)"
priority: high
depends_on: [task_13_b07_truncated_count_ux]
source_reference: ".ai/plans/13-performance-remediation.md"
source_section: "BLOCK 8 - rollup_daily_metrics: the write loop, without touching the lock"
source_blocks: ["BLOCK 8"]
description: >
  rollup_daily_metrics opens one transaction.atomic() and takes
  advisory_lock(ROLLUP_DAILY_METRICS) around a loop of DailyAdMetrics.update_or_create calls - one
  per ad per day, ~120000 statements in one ~305 s transaction by the report's measurement. The
  unique constraint uq_daily_ad_metrics_ad_date is verified present, so a chunked
  bulk_create(update_conflicts=True, unique_fields=[...], update_fields=[...]) is the right
  instrument and reuses an existing Django idiom. The report's per-statement attribution and its
  "a few seconds" projection are not accepted and are not repeated. The real cost is not the
  duration but that the advisory lock is held for its whole duration.
goals:
  - "the per-row upsert loop is replaced by a chunked bulk upsert against the existing unique constraint"
  - "the advisory lock, its placement inside the transaction, and its session scope are byte-identical"
  - "before/after statement counts are recorded, and durations are measured or explicitly not measured"
extra_context: |
  BINDING CONSTRAINTS
  1. The advisory lock is untouchable: exactly one per command, in_atomic_block True, session
     False. Phase 13 allocates NO AdvisoryLockId; next free integer is 14. Do not touch
     test_advisory_lock_ids.py.
  2. Preserve the transaction shape - one transaction.atomic() around the command's work, taken
     inside the lock as today. Whether the whole sweep should be one transaction is DB-008 and is
     phase 03's. Do not pre-empt it.
  3. update_conflicts=True needs an EXACT constraint match. Record the constraint's name and where
     it was verified in the commit body.
  4. --dry-run still writes nothing and reports the same summary.
  5. Measure before/after against a PRODUCTION-SIZED dataset on a PRIVATE instance. Never the
     shared test database. The report's "305 s -> a few seconds" is NOT a promise this block
     makes. If a duration cannot be measured, say "not measured" and report only the
     statement-count reduction, which is statically derivable.
  6. NO MIGRATION. If the fix appears to need a constraint change, stop and report.
  7. No print(); progress output is logger.info with lazy %s and carries no ad content.
  GATE Q10 (bulk_create safety against the real constraint) MUST be answered in writing before
  implementation. The Implementor is forbidden from choosing an option.
  CITATION: "PERF-003 (validated 2026-09)".
files:
  - path: src/backend/apps/analytics/management/commands/rollup_daily_metrics.py
    targets:
      - type: function
        name: handle
    changes:
      - "Replace the per-row update_or_create loop with a chunked bulk_create upsert against the existing unique constraint. The dry-run branch is unchanged."
  - path: src/backend/apps/analytics/tests/test_rollup_daily_metrics.py
    targets:
      - type: module
        name: test_rollup_daily_metrics
    changes: []
changes:
  - action: add_code
    description: >
      Add a test that runs the rollup twice over the same data and asserts the second run updates
      the existing rows rather than creating duplicates or silently dropping the update, plus a
      test that a conflicting concurrent value is resolved by the constraint.
acceptance_criteria:
  - "the second run updates in place; no duplicate rows and no silently dropped update"
  - "exactly one advisory_lock remains, in_atomic_block is True and session is False, demonstrated by test_sweep_lock_structure staying green"
  - "the before/after statement counts are recorded, with the measurement environment named; any duration is either measured with its command or explicitly marked not measured"
  - "the commit body does not repeat the report's 305 s -> a few seconds projection"
  - "no migration was written and no constraint was altered"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/analytics/tests
  - src/backend/apps/core/tests/test_sweep_lock_structure.py
  - src/backend/apps/core/tests/test_advisory_lock_ids.py
```

---

### BLOCK 9 — `send_alerts`: group the daily loop, and do not touch a reserved file blind (`PERF-005`)

| | |
|---|---|
| **Findings owned** | `PERF-005` (MEDIUM) |
| **Class** | **behavioural** — result-set construction changes inside a lock-held transaction |
| **Depends on** | BLOCK 8 (soft, ordering); **Q11** (hard — the reservation must be re-read) |
| **Blocks** | nothing in this plan |
| **Priority** | **P2** |
| **Risk level** | **MEDIUM.** Grouping changes how results are assembled, and the per-search structural filters and the 10-per-digest cap are **not** interchangeable with a global cap |
| **Blast radius** | the daily alert command and — **if the grouping reaches it** — `alert_query.py`, which is a **three-way reservation** |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**The defect, and the correction of its severity.** `Command._collect_alerts` calls
`find_matching_ads(saved_search)` once per saved search — one FTS evaluation each — and the
daily path runs inside `transaction.atomic()` **and** `advisory_lock(ALERT_DELIVERY_TASK)`. ✔ The
report's "monopolising" framing is **refuted**: the loop is linear and bounded, and 1 000
searches against `SCHEDULER_COMMAND_TIMEOUT = 1 800 s` is ~190 s. The finding stands as a
**shape** problem plus a **lock-duration** problem, not an outage.

**The three-way reservation (Q11).** `apps/search/services/alert_query.py` is claimed by
**phase 06 BLOCKS 5/7** (eligibility) and **phase 03 BLOCK 9** (delivery state). **Phase 13
claims none.** If either has landed, the function's contract may have changed and the grouping
must be written against what is actually there. **The Implementor must re-read the file
immediately before editing and report if it has changed** — this is not optional, and it is the
reason this block requires a Researcher.

**Alternatives for the grouping, with trade-offs:**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| (a) | Group saved searches by distinct `(language, query)`; evaluate once per group; apply the per-search structural filters and the 10-per-digest cap **per member** after the shared evaluation | The cap stays per-search, so no digest silently widens | **Good** — the shared work is the FTS evaluation, which is what actually repeats | ✔ Reuses `find_matching_ads` unchanged | If the structural filters are applied once instead of per member, two saved searches with different filters silently share results. **This is the tripwire** |
| (b) | Batch by `(language, query)` **and** merge the structural filters into the query | Fewer evaluations still | Poor — merged filters are not composable (OR vs AND) | ✘ Changes `alert_query`'s contract, which is reserved | A notification fires for an ad that does not match that user's saved filter |
| (c) | Leave the loop; add progress logging only | Zero risk | Poor — the cost is unchanged | ✔ | The finding is only half-closed |
| (d) | Move the collection outside the transaction | The FTS work no longer holds the lock | **Good**, and it is the real lock-duration fix | ✔ | A longer-lived snapshot is lost; whether that matters is a **semantic** decision, not a performance one, and it is `DB-008`'s territory |

**This Planner's floor: (a) plus the tripwire that proves per-search filters are preserved.
Logging alone is not a remediation of a finding whose subject is the loop's shape.**

**Binding constraints**

1. **The advisory lock is untouched** — one per command, `in_atomic_block is True`,
   `session is False` (`test_sweep_lock_structure`). **Phase 13 allocates no lock id.**
2. **`alert_query.py` is re-read immediately before any edit, and the reservation is reported.**
   If phase 06 or phase 03 has landed, **the block stops and reports** rather than assuming.
3. **The 10-per-digest cap stays per-search.** `_DIGEST_AD_LIMIT` bounds one user's digest, not a
   group's. A group that shares a query does **not** share a cap.
4. **No notification is sent that was not sent before, and none is dropped.** A digest's
   composition must be identical before and after for the same data — that is the tripwire, and
   it covers both the grouping and the structural filters.
5. **The immediate-alert path is a separate concern** and is **out of scope** here; the report
   notes it is not batched, and changing it is `DB-008`/phase 03's call.
6. **Progress logging is `logger.info`, lazy `%s`, and value-free** — a saved search's query text
   must be sanitized through the existing `sanitize_query_for_log` if it is logged at all.

**Implementor task**

```yaml
id: task_13_b09_send_alerts_grouping
title: "Group the daily alert collection by distinct (language, query) without widening the per-digest cap (13 PERF-005, validated 2026-09)"
priority: medium
depends_on: [task_13_b08_rollup_bulk_upsert]
source_reference: ".ai/plans/13-performance-remediation.md"
source_section: "BLOCK 9 - send_alerts: group the daily loop"
source_blocks: ["BLOCK 9"]
description: >
  _collect_alerts calls find_matching_ads once per saved search - one FTS evaluation each - and
  the daily path runs inside transaction.atomic() and advisory_lock(ALERT_DELIVERY_TASK), so the
  lock is held for the whole loop. The loop is linear and bounded against the 1800 s command
  timeout, so the finding is a shape and lock-duration problem, not an outage. Group the saved
  searches by distinct (language, query), evaluate the FTS once per group, and apply each
  member's structural filters and its own 10-ad cap afterwards so no digest silently widens.
goals:
  - "the number of FTS evaluations equals the number of distinct (language, query) pairs, not the number of saved searches"
  - "a digest's composition is byte-identical before and after for the same data"
  - "the advisory lock and transaction shape are unchanged"
extra_context: |
  BINDING CONSTRAINTS
  1. The advisory lock is untouchable: one per command, in_atomic_block True, session False.
     Phase 13 allocates NO AdvisoryLockId.
  2. alert_query.py is a THREE-WAY RESERVATION (phase 06 BLOCKS 5/7 eligibility, phase 03 BLOCK 9
     delivery state, phase 13 none). Re-read it immediately before any edit and report if it has
     changed. If either phase has landed, STOP and report rather than assuming.
  3. _DIGEST_AD_LIMIT stays PER-SEARCH. Two saved searches sharing a query do NOT share a cap.
  4. No notification is sent that was not sent before, and none is dropped. Digest composition
     must be identical for the same data - that is the tripwire.
  5. The immediate-alert path is OUT OF SCOPE; batching it is DB-008 and phase 03's call.
  6. Progress logging is logger.info with lazy %s. Sanitize any logged query text through
     sanitize_query_for_log.
  7. Batching writes on the immediate path is explicitly not this block.
  GATE Q11 (grouping key and the reservation re-read) MUST be answered in writing before
  implementation. The Implementor is forbidden from choosing an option.
  CITATION: "PERF-005 (validated 2026-09)".
files:
  - path: src/backend/apps/search/management/commands/send_alerts.py
    targets:
      - type: function
        name: _collect_alerts
    changes:
      - "Group by distinct (language, query); evaluate once per group; apply per-member structural filters and per-member caps."
  - path: src/backend/apps/search/tests/test_send_alerts.py
    targets:
      - type: module
        name: test_send_alerts
    changes: []
changes:
  - action: add_code
    description: >
      Add a test with two saved searches sharing a query but differing in a structural filter,
      asserting each receives exactly the ads its own filter admits, and a test asserting the FTS
      evaluation count equals the distinct-pair count.
acceptance_criteria:
  - "digest composition is byte-identical before and after for the same data, demonstrated"
  - "two saved searches sharing a query but differing in a structural filter do NOT share results"
  - "the FTS evaluation count equals the distinct (language, query) count, asserted"
  - "test_sweep_lock_structure and test_advisory_lock_ids are green and untouched"
  - "alert_query.py's reservation state is recorded in the commit body"
  - "no print(); any logged query text is sanitized"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/search/tests
  - src/backend/apps/core/tests/test_sweep_lock_structure.py
  - src/backend/apps/core/tests/test_advisory_lock_ids.py
  - src/backend/apps/ads/tests/test_search_triggers.py
```

---

### BLOCK 10 — The observability gap, in a file phase 12 owns (`PERF-011`, observability half)

| | |
|---|---|
| **Findings owned** | `PERF-011` — **observability half only.** The capacity half is **rejected upstream and not re-litigated here** |
| **Class** | **behavioural** — an alert rule's selector set changes |
| **Depends on** | BLOCK 9 (soft, ordering) · **Q12** (hard — coordinator sequencing) |
| **Blocks** | nothing in this plan |
| **Priority** | **P2** |
| **Risk level** | **LOW in YAML, HIGH in consequence.** An alert that fires on nothing is worse than no alert, and the file already contains three rules whose selectors this validation found to be unresolvable |
| **Blast radius** | `docs/ops/prometheus-slo-alerts.yaml` — **phase 12 BLOCK 11's file** |
| **Required agents** | **Auditor · Planner · Validator** — all four (Researcher optional) |

**What phase 13 is allowed to do here, and what it is not.** The alert-scope gap is real and
free to close: the burn-rate and p95 rules select `handler="search:search"` and nothing covers
the listings path. ✔ **`ENT-001` has shipped** (C-3) — phase 01 delivered `child_exit`,
`PROMETHEUS_MULTIPROC_DIR`, the tmpfs and the `test_compose_contract.py` assertions — so the
original "sequence after `ENT-001`" constraint is **discharged**. ✔ The file's multiprocess
caveat is **stale** (C-4) — and **phase 12 BLOCK 11 corrects it. Phase 13 does not.**

**The capacity half is rejected, and the reason is worth stating because it is counterintuitive.**
The report proposes raising gunicorn `workers`. `web` ships `cpus: ${WEB_CPUS:-1.5}` and
`mem_limit: ${WEB_MEM_LIMIT:-512m}`, and **no `.env.*` file overrides either**. "A worker count
near the core count" therefore means **1–2 — fewer than today's 3**, on a workload the
measurement put at 74 % CPU. The proposal makes the declared ceiling *lower*. **It is not
implemented, and phase 13 has no `gunicorn.conf.py` edit at all.**

**File surface and the reservation.** `docs/ops/prometheus-slo-alerts.yaml` has
**phase 12 BLOCK 11** as its owner (`OPS-003`), which is currently *making the alert file a
verified contract* — that is, it is correcting selectors, adding a scrape-contract test, and
removing or keeping the monitoring stack depending on its own gate. **Editing the same file from
two phases in one window is a merge hazard, not a collaboration.**

**Alternatives for sequencing, with consequences:**

| Option | Shape | Consequence |
|---|---|---|
| (a) | **Sequential** — phase 13 waits for phase 12 BLOCK 11 to land, then extends the scope on top of the corrected file | One review window, no conflict. **This is the only option this plan can recommend.** It makes BLOCK 10 **externally gated** |
| (b) | Parallel edits to disjoint rule blocks | Both agents read the same file; one commit is reviewed against a state that no longer exists. The failure is silent |
| (c) | Phase 13 writes the scope extension as a **separate proposed fragment** in the commit body and lands nothing | Zero conflict, and the work is done — but nothing is enforced. The finding stays open until someone applies it |

**This Planner's position: (a).** BLOCK 10 does not start until phase 12's block has landed or
the coordinator has explicitly sequenced them. Under (c) the block still ships a reviewed,
correct fragment — it simply ships no file.

**The metric-identity trap, stated so nobody builds on it (Q12).** `cache_hit_rate_slo` reads
**Redis keyspace hits**, not application cache hits. It is **~100 % by construction** and it is
**not** a measure of the search cache. **Phase 12 owns the selector correction; phase 13 must
not build on that metric, and must not add a rule that references it.**

**Binding constraints**

1. **The file is not edited until phase 12 BLOCK 11 has landed**, or the coordinator has
   sequenced them. Report the state; do not assume it.
2. **Phase 12's corrections are not restated, re-applied or "corrected again".** If the file
   still carries the stale multiprocess caveat when phase 13 reaches it, that is a **report to
   the coordinator**, not an edit — the same file in two states is the hazard this block exists
   to avoid.
3. **Every selector this block adds must resolve against a rendered `/metrics`**, and the
   scrape-contract test must be extended to police it — the `test_metrics_endpoint` precedent.
   A selector naming a series that does not exist **must turn the test red**.
4. **No new rule may reference `cache_hit_rate_slo`,** and no new rule may depend on a metric
   phase 12 has marked untrustworthy.
5. **No gunicorn `workers` change, no `WEB_CPUS` / `WEB_MEM_LIMIT` change, no env key.**
   `test_env_allowlist.py` is untouched and green. Phase 12's BLOCK 11 and BLOCK 12 own the
   alert set; phase 13 extends scope and nothing else.
6. **If phase 12 declined to deploy a monitoring stack** (its own gate), the added rules have no
   consumer. Say so in the commit body and record the finding as **detection-inert but
   contract-correct**, rather than claiming coverage.

**Implementor task**

```yaml
id: task_13_b10_alert_scope_extension
title: "Extend the latency SLO alert scope beyond the search view, after phase 12 has corrected the file (13 PERF-011 observability half, validated 2026-09)"
priority: medium
depends_on: [task_13_b09_send_alerts_grouping, phase12_block11_slo_contract]
source_reference: ".ai/plans/13-performance-remediation.md"
source_section: "BLOCK 10 - The observability gap, in a file phase 12 owns"
source_blocks: ["BLOCK 10"]
description: >
  The burn-rate and p95 rules in docs/ops/prometheus-slo-alerts.yaml select
  handler="search:search" and nothing covers the listings path, so the buyer-critical page that
  carries the header N+1 fixed in BLOCK 5 is unmonitored. Phase 01's ENT-001 has shipped, so
  the original "sequence after ENT-001" constraint is discharged. The file itself is phase 12
  BLOCK 11's, which is currently correcting its selectors, correcting the stale multiprocess
  caveat and adding a scrape-contract test - so the extension is sequential with it, not
  parallel. The capacity half of this finding is rejected: web ships cpus 1.5 with no env
  override, so "a worker count near the core count" means fewer than today's three.
goals:
  - "the latency SLO rules cover the listings path as well as search, with selectors that resolve against a rendered /metrics"
  - "a selector naming a series that does not exist turns the scrape-contract test red"
  - "no new rule references cache_hit_rate_slo, which reads Redis keyspace hits and is ~100% by construction"
extra_context: |
  BINDING CONSTRAINTS
  1. Do not edit docs/ops/prometheus-slo-alerts.yaml until phase 12 BLOCK 11 has landed, or the
     coordinator has explicitly sequenced them. Report the state; do not assume it.
  2. Do NOT restate or re-correct phase 12's fixes. If the stale multiprocess caveat is still
     present when this block runs, REPORT it to the coordinator - do not edit it.
  3. Every selector added must resolve against a rendered /metrics, and the scrape-contract test
     must be extended to police it. test_metrics_endpoint is the precedent.
  4. No new rule may reference cache_hit_rate_slo.
  5. NO gunicorn workers change, NO WEB_CPUS / WEB_MEM_LIMIT change, NO env key.
     test_env_allowlist.py is untouched and green. The capacity half of PERF-011 is REJECTED.
  6. If phase 12 declined to deploy a monitoring stack, say so and record the finding as
     detection-inert but contract-correct. Do not claim coverage.
  GATE Q12 (alert scope and cross-phase sequencing) MUST be answered in writing before
  implementation. The Implementor is forbidden from choosing an option.
  CITATION: "PERF-011 observability half (validated 2026-09)".
files:
  - path: docs/ops/prometheus-slo-alerts.yaml
    targets:
      - type: alert
        name: search_slo_burn_rate
      - type: alert
        name: search_p95_latency_slo
    changes:
      - "Extend the selector set to the listings handler. Every added selector must resolve against a rendered /metrics."
  - path: src/backend/apps/core/tests/test_observability.py
    targets:
      - type: function
        name: test_metrics_endpoint
    changes:
      - "Extend beside it, never rewriting it or disturbing the multiprocess assertions."
changes:
  - action: add_code
    description: >
      Add selectors for the listings path and demonstrate the scrape-contract test turning red
      when a selector naming a non-existent series is added.
acceptance_criteria:
  - "every selector in the file resolves against a rendered /metrics, and a deliberately dead selector turns the guard red - demonstrated"
  - "no new rule references cache_hit_rate_slo"
  - "phase 12 BLOCK 11's landing state is recorded in the commit body; no phase-12 correction was restated"
  - "no gunicorn, compose, env or allowlist change; test_env_allowlist is untouched and green"
  - "if phase 12 declined a monitoring stack, the commit body says the rules have no consumer and does not claim coverage"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/core/tests/test_observability.py
  - src/backend/tests/test_compose_contract.py
  - config/settings/tests/test_env_allowlist.py
```

---

### BLOCK 11 — The duplicate `cities` query, and nothing else (`PERF-008`)

| | |
|---|---|
| **Findings owned** | `PERF-008` — **positive-ROI limb only** |
| **Class** | **mechanical** |
| **Depends on** | BLOCK 10 (soft, ordering) |
| **Blocks** | nothing |
| **Priority** | **P3** — last of the code blocks |
| **Risk level** | **LOW**, with one sharp edge: a context-key change can blank a dropdown if the key is removed rather than de-duplicated |
| **Blast radius** | the search view's template context |
| **Required agents** | **Validator** (Auditor/Researcher/Planner not required — the defect is confirmed, the fix is one key, and the target is settled by C-7) |

**The defect, after the tree correction (C-7).** ✔ The report's Required-Fixes #13 says "remove
the duplicate `save_search_cities` at `search.py:217`". **There is no `save_search_cities`
anywhere in `src/`.** The real situation: `context_processors.header_context` returns
`"cities": list(City.objects.order_by("name"))` and runs on every request, while `search()`'s
context dict **independently sets** `"cities": City.objects.order_by("name"))` — a second query
for the same rows, and a shadowed context key. That duplicate is the only limb with positive ROI
today.

**What is deliberately not done, and why:**

- **The header's `cities` list is not cached.** The shipped list is **15 rows** (~8 KB,
  ~0.2 ms). Every headline figure in the finding came from **5 015 injected rows**. Caching 15
  rows is overengineering (rule 3), and the city-data source is a **phase 06/07 decision** —
  phase 13 would be caching a list whose contents are still being decided.
- **The reported 2.9 MB page and 61 ms query are not repeated anywhere**, in any doc or commit
  message. They are refuted as a shipped cost (§0.2.3 row 6).

**Alternatives, with trade-offs:**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| (a) | Remove the redundant `cities` key from `search()`'s context; the header processor's value is the one that renders | One source of truth for the key; the query runs once | **Good** — and it makes the phase 06/07 city-data decision land in exactly one place | ✔ Smallest correct change | A template that relies on `search()`'s key still works **only because the processor provides it**. The test must prove that |
| (b) | Keep the view's key, remove the header's | Same count | **Poor** — the header runs on pages with no `search()` context, so its value is the load-bearing one | ✘ | Every non-search page loses its city list |
| (c) | Cache the list | Zero queries | Poor — caches 15 rows | ✘ Overengineering (rule 3) | A new mechanism with its own invalidation, for 0.2 ms |

**Binding constraints**

1. **The removal is a deletion of the duplicate key, not a rename and not a cache.** The
   header processor's value must continue to render — assert it, do not assume it.
2. **`_DIGEST`/filter-option context keys are untouched.** Only `cities` is in scope.
3. **No number from the 5 015-row scenario may be quoted** in a comment, a docstring, or a
   commit body.
4. **No cache, no settings key, no env key.** If the block appears to need one, that is a
   report, not an edit.
5. **`test_listings_context` and `test_search_query_count` are the tripwires** and must stay
   green — the first includes the header.

**Implementor task**

```yaml
id: task_13_b11_duplicate_cities
title: "Remove the duplicate cities context key from the search view (13 PERF-008, validated 2026-09)"
priority: low
depends_on: [task_13_b10_alert_scope_extension]
source_reference: ".ai/plans/13-performance-remediation.md"
source_section: "BLOCK 11 - The duplicate cities query, and nothing else"
source_blocks: ["BLOCK 11"]
description: >
  header_context returns "cities": list(City.objects.order_by("name")) on every request, and
  search()'s context dict independently sets the same "cities" key with the same query - a
  second query for the same rows and a shadowed key. That duplicate is the only limb of PERF-008
  with positive ROI: the shipped city list is 15 rows (~8 KB, ~0.2 ms), and every headline figure
  in the finding came from 5015 injected rows. The source report's prescribed target,
  save_search_cities, does not exist anywhere in src/ - the real key is "cities". Caching the
  header list is de-scoped: the city-data source is a phase 06/07 decision.
goals:
  - "the cities query runs once per request, not twice"
  - "the header city dropdown still renders from the context processor's value, asserted not assumed"
extra_context: |
  BINDING CONSTRAINTS
  1. This is a deletion of a duplicate key, not a rename and not a cache. Assert that the
     header still renders the city list from the processor's value.
  2. Only "cities" is in scope. Every other filter-option context key is untouched.
  3. No number from the 5015-row scenario may be quoted in a comment, docstring, or commit body.
  4. No cache, no settings key, no env key. If one appears necessary, report it.
  5. The report's save_search_cities target does not exist - do not go looking for it or create
     it.
  CITATION: "PERF-008 (validated 2026-09)".
files:
  - path: src/backend/apps/search/views/search.py
    targets:
      - type: function
        name: search
      - type: context_key
        name: cities
    changes:
      - "Remove the duplicate cities key. The header_context value renders instead."
  - path: src/backend/apps/ads/tests/test_listings_context.py
    targets:
      - type: module
        name: test_listings_context
    changes:
      - "Assert the city list still renders and the query is not issued twice."
changes:
  - action: add_code
    description: >
      Add a test asserting the header city dropdown renders its full contents on a search
      response, and that the cities query appears once in the captured queries. Demonstrate the
      duplicate turning the guard red before the change.
acceptance_criteria:
  - "the city list renders completely on a search response, asserted not assumed"
  - "the cities query appears exactly once in the captured queries for a search request"
  - "no other context key changed; no cache, settings key or env key introduced"
  - "no figure from the 5015-row scenario appears anywhere"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/ads/tests/test_listings_context.py
  - src/backend/apps/search/tests/test_search_query_count.py
  - src/backend/apps/ads/tests/test_ad_detail_queries.py
```

---

### BLOCK 12 — Cheapest last: the profiler's documentation and the on-demand sweep's cost (`PERF-015` docs half, `PERF-013`)

| | |
|---|---|
| **Findings owned** | `PERF-015` (documentation half), `PERF-013` (cost quantification only) |
| **Class** | **mechanical** |
| **Depends on** | **BLOCK 11** (hard, so the documented numbers describe a finished phase) |
| **Blocks** | nothing |
| **Priority** | **P3** — last block in the plan |
| **Risk level** | **LOW** — documentation and measurement, no behaviour change |
| **Blast radius** | `docs/ops/profiling.md`; one management command's reported cost |
| **Required agents** | **Validator** |

**Why documentation is the last block and not the first.** Every number `docs/ops/profiling.md`
and every cost in `PERF-013` describes a system that BLOCKS 1–11 have changed. Documenting first
would encode numbers this phase invalidates. **This is the phase-12 BLOCK 14 → BLOCK 15 rule in
a different costume: the truth sweep lands after every code change it documents, and any parity
guard lands after the truth.**

**`PERF-015` — what survives, and what is refuted.** ✔ Claim 1 is **refuted**: `make profile` runs
`scripts/profile_search.py` (cProfile), **not** `profile_queries`; the doc presents them as two
tools and **correctly** states the 10 k skip at its own line. What survives is real:

- `_build_queries()` omits the production-path shapes — **now fixed in BLOCK 3**; the doc must
  describe the fixed tool.
- The threshold is a **table-size** axis while FTS cost scales with **match count** — the
  correctness point of Q4, which BLOCK 3 answered. The doc must describe **the axis that
  shipped**, not the one the report preferred.
- The `make up` claim is **false** — **verify and correct it**, do not delete it silently.
- The "best signal" wording is **too strong** for a tool whose skip path used to print green;
  the doc must say what the tool can and cannot tell you.

**`PERF-013` — cost quantification only, and the boundary is hard.** ✔
`recompute_normalized_prices._process_batch` holds `select_for_update`; the command wraps its
sweep in one `transaction.atomic()`; and it is **absent from both `HOURLY_COMMANDS` and
`DAILY_COMMANDS`**, so it runs only on demand. The transaction shape is **`DB-008` and phase
03's** — `archive_sweep` and `recompute_normalized_prices` are rewritten by phase 03 BLOCK 7.
**Phase 13 measures and records; it does not restructure.** ✔
`test_recompute_command.py::test_process_batch_uses_select_for_update` inspects `_process_batch`'s
source for `select_for_update`, and `TestRecomputeRowLockConcurrency` holds a row lock for ~1 s
and asserts a concurrent edit blocks. **This block touches neither**, and a block that appears
to need to re-point them is out of bounds.

**Binding constraints**

1. **`recompute_normalized_prices`'s transaction shape, `_process_batch`, and its lock are
   untouched.** Measurement only.
2. **No `statement_timeout` / `lock_timeout` is proposed or added.** `DB-004` is **phase 03's**
   and is a **co-equal P0 with `SRCH-001`** after this phase's own WAL-redo finding (`VAL-001`).
   The documentation may **reference** that; it may not implement it. **Note for the reader:**
   `test_recompute_command.py::TestRecomputeRowLockConcurrency`, `test_sweep_archive.py` and
   `test_transition_concurrency.py` all hold locks for ~1 s and **break under a global
   `lock_timeout` below that** — which is why phase 03 must choose per-role. **Phase 13 records
   this and changes nothing.**
3. **Every number in the doc is one a command in this repository can produce.** If the block
   cannot produce it, the doc does not carry it.
4. **The doc describes the tool BLOCK 3 shipped**, including the non-zero exit on skip. It does
   not describe the tool as it was.
5. **No `makemessages`, no locale regeneration, no `statement_timeout`, no env key.**
6. **`docs/architecture/cache-strategy.md` is not edited here** — it is phase 08's and BLOCK 4's.

**Implementor task**

```yaml
id: task_13_b12_profiling_docs_and_sweep_cost
title: "Correct docs/ops/profiling.md to describe the shipped tool, and record recompute_normalized_prices' cost without changing it (13 PERF-015 + PERF-013, validated 2026-09)"
priority: low
depends_on: [task_13_b11_duplicate_cities]
source_reference: ".ai/plans/13-performance-remediation.md"
source_section: "BLOCK 12 - Cheapest last"
source_blocks: ["BLOCK 12"]
description: >
  docs/ops/profiling.md documents two tools and states that make profile runs scripts/profile_search.py
  (cProfile) rather than profile_queries; the false "make up" claim and the over-strong "best
  signal" wording survive, and the tool description is now out of date because BLOCK 3 changed
  the threshold flag, the query shapes and the exit code. Separately, recompute_normalized_prices
  is absent from HOURLY_COMMANDS and DAILY_COMMANDS, runs only on demand, and its cost is
  quantifiable but its transaction shape belongs to DB-008 in phase 03. Correct the
  documentation to describe the tool as it now ships, and record the command's measured cost
  without changing it.
goals:
  - "the documentation describes the tool BLOCK 3 shipped, including the non-zero exit on skip"
  - "the false make up claim and the over-strong best-signal wording are corrected to what the tool can actually tell you"
  - "recompute_normalized_prices' cost is recorded from a command, with no change to the command"
extra_context: |
  BINDING CONSTRAINTS
  1. recompute_normalized_prices' transaction shape, _process_batch, and its select_for_update
     are UNTOUCHED. This is measurement only. Do not re-point
     test_recompute_command.py::test_process_batch_uses_select_for_update or
     TestRecomputeRowLockConcurrency.
  2. NO statement_timeout and NO lock_timeout is proposed or added - DB-004 is phase 03's and is a
     co-equal P0 with SRCH-001. You may reference it. Record that
     test_recompute_command.py::TestRecomputeRowLockConcurrency, test_sweep_archive.py and
     test_transition_concurrency.py hold locks for ~1 s and break under a global lock_timeout
     below that. Change nothing.
  3. Every number in the doc is one a command in this repository can produce. If the block
     cannot produce it, the doc does not carry it.
  4. Describe the tool as BLOCK 3 shipped it - threshold flag, production shapes, non-zero exit
     on skip - not as it was.
  5. No makemessages, no locale regeneration, no env key. docs/architecture/cache-strategy.md is
     NOT edited here.
  CITATION: "PERF-015 (validated 2026-09)" and "PERF-013 (validated 2026-09)".
files:
  - path: docs/ops/profiling.md
    targets:
      - type: section
        name: profiling tools
    changes:
      - "Describe both tools accurately; correct the false make up claim; soften best-signal wording; document the shipped threshold flag and the non-zero exit on skip."
  - path: src/backend/apps/currencies/management/commands/recompute_normalized_prices.py
    targets:
      - type: function
        name: handle
    changes: []
changes:
  - action: modify_code
    description: >
      None to the command. Record its measured cost in the documentation with the exact command
      that produced it, and state explicitly that it runs on demand only.
acceptance_criteria:
  - "the documentation names both tools and states which one make profile runs"
  - "the false make up claim is corrected to a verified statement about what the command does"
  - "the best-signal wording states what the tool can and cannot tell you, including the skip path"
  - "the shipped threshold flag and the non-zero exit on skip are documented"
  - "recompute_normalized_prices is byte-identical; test_recompute_command and test_edit_views_locking are green and untouched"
  - "no statement_timeout, lock_timeout, env key, or locale file was added"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/currencies/tests/test_recompute_command.py
  - src/backend/apps/ads/tests/test_edit_views_locking.py
  - src/backend/apps/core/tests/test_sweep_lock_structure.py
  - config/settings/tests/test_env_allowlist.py
```

---

## 4. Dependency graph

### 4.1 Execution order (the safe serial order)

One Implementor, strictly sequential. Every block is one commit (§1.3). The numbering *is* the
order, and the order answers one question: **what must be true before the next change can be
trusted?**

| # | Block | Findings | Class | Depends on (in-plan) | Gate | Risk |
|---|---|---|---|---|---|---|
| 1 | Make the p95 gate real | `PERF-001` (+`PERF-012c`) | **S** | — | **Q1, Q2** | **HIGH** |
| 2 | The load test must be real | `PERF-012a` | B | 1 | **Q3** | MED |
| 3 | The profiler must be honest | `PERF-012b`, `PERF-015` (tool) | M | 2 (soft) | **Q4** | LOW–MED |
| 4 | Version-key lifetime invariant | `SRCH-007` TTL limb | **S** | — | **Q5** + **phase 08 BLOCK 6** | **HIGH** |
| 5 | The three N+1s, one change | `PERF-004`, `PERF-009`, `PERF-014` | B | 4 | **Q6, Q7** | **HIGH** |
| 6 | Cap in SQL, page-scoped rank | `PERF-006` #1, `PERF-010` | B | 5 | **Q8** | MED |
| 7 | Truncated-count UX | `PERF-006` #2 | **B** | 6 | **— (was `Q9`; RESOLVED 2026-10-03)** | **MED** (user-visible; was HIGH) |
| 8 | `rollup_daily_metrics` bulk upsert | `PERF-003` | B | 7 (soft) | **Q10** | MED |
| 9 | `send_alerts` grouping | `PERF-005` | B | 8 (soft) | **Q11** | MED |
| 10 | Alert scope extension | `PERF-011` (obs. half) | B | 9 (soft) | **Q12** + **phase 12 BLOCK 11** | LOW / **HIGH** if unsequenced |
| 11 | The duplicate `cities` key | `PERF-008` | M | 10 (soft) | — | LOW |
| 12 | Docs + on-demand sweep cost | `PERF-015` (docs), `PERF-013` | M | 11 | — | LOW |

`M` = mechanical · `B` = behavioural · `S` = structural · `C` = conditional.

### 4.2 The DAG and why each edge exists

```
  (none) --> [1 p95 gate] --Q1,Q2--> [2 load test real] --Q3--> [3 profiler honest] --Q4
                 |                                                                          |
                 |                             (no in-plan edge)                              |
                 |                                                                          v
                 |                                                   [4 version-key TTL] --Q5
                 |                                                          |              (phase 08 BLOCK 6)
                 |                                                          v
                 |                                                   [5 three N+1s, one change] --Q6,Q7
                 |                                                          |
                 |                                                          v
                 |                                                   [6 cap in SQL + page rank] --Q8
                 |                                                          |
                 |                                                          v
                 |                                                   [7 truncated-count UX] --Q9 RESOLVED 2026-10-03
                 |                                                          |
                 |                                                          v
                 |                                                   [8 rollup bulk upsert] --Q10
                 |                                                          |
                 |                                                          v
                 |                                                   [9 send_alerts grouping] --Q11
                 |                                                          |
                 |                                                          v
                 +--> [10 alert scope] --Q12 (phase 12 BLOCK 11) --> [11 duplicate cities]
                                                                             |
                                                                             v
                                                                      [12 docs + sweep cost]
```

**Each edge, with the reason it exists:**

| Edge | Kind | Why it exists |
|---|---|---|
| **1 → 2** | hard, dependency | ✔ `VAL-004` item 1 and the report's rollout row 4: *"Re-baseline the p95 afterwards, **after** fix 1."* Fixing the URLs makes the measured p95 **materially worse** — the current number includes 404s, which are fast. Reading a worse p95 off a broken gate is meaningless. **This is the phase's only non-negotiable ordering claim** |
| **1 → everything** | hard, gate | ✔ Every other finding in this phase is a regression a working gate would have to catch. The gate lands first so a later block's red step is unambiguously its own. **It is also the guard against the `locust>=2.20.0` drift** (C-8) |
| **2 → 3** | soft, ordering | No file overlap. `profile_queries` does not depend on the locust fix. Placed here so the re-baseline BLOCK 3 enables is taken from a fixed harness. **Soft** — BLOCK 3 would be correct in any position |
| **(none) → 4** | **hard, external** | ✔ BLOCK 4's gate is **phase 08 BLOCK 6's landing state**. It is not a soft edge to BLOCK 3: it is a dependency on work in another plan. If phase 08's block has not landed, Q5's answer must say whether retuning means anything at all, because phase 08's change would immediately re-open the window. **`Q5` is still GATED after the 2026-10-03 round (it is a technical gate, deliberately left open) and MUST be re-read at implementation time: landed ⇒ retune; not landed ⇒ the answer must say so explicitly** |
| **4 → 5** | hard, file | ✔ Both touch the **submenu TTL surface**: BLOCK 4 may adjust `SUBMENU_CACHE_TTL`/`STALE_TTL` under Q5(c), and BLOCK 5's `mega_submenu` limb annotates the fragment those TTLs govern. Running 5 first means its annotation lands on TTLs that are about to move |
| **3 ↔ 4** | **no edge** | Different surfaces: `profile_queries` and the cache services share no file, no constant, no test. Making an edge would serialise two blocks that are independently correct |
| **5 → 6** | hard, dependency | ✔ `VAL-004` item 4: the three N+1-bound findings are **one change**, or `_QUERY_BOUND` publishes a number nobody measured. BLOCK 6 then re-measures the search view — and it can only interpret its result against a bound BLOCK 5 has re-derived |
| **6 → 7** | hard, dependency | ✔ #2 changes what `_resolve_search_count` **returns**; #1 changed how it obtains the value. Landing #2 first means it is written against a `COUNT(*)` path BLOCK 6 has already removed |
| **6, 7 → 8/9** | soft, ordering | No file overlap — 8 and 9 are management commands, 6 and 7 are the search view. Placed after so the **request path is finished** before the background paths are touched, and so the request-path gates (Q7, Q8) are resolved while the Implementor's context is fresh. **Soft** — 8 and 9 would be correct in any position |
| **9 → 10** | soft, ordering | No file overlap. `send_alerts` and the alert YAML are unrelated. Placed here because the alert rules cover the **listings path**, and BLOCK 5 changed that path's query inventory — the rules should be scoped against a settled path |
| **10 → 11** | soft, ordering | No file overlap. `search()`'s context and the alert file share nothing. **Soft** — 11 is the cheapest block in the plan and is placed late only so the alert question is not left dangling |
| **11 → 12** | hard, dependency | ✔ The same rule as phase 12's BLOCK 14 → 15: **the truth sweep lands after every code change it documents.** `docs/ops/profiling.md` describes a system that BLOCKS 1–11 have changed. Documenting first encodes numbers this phase invalidates. **There is no soft variant of this edge** |
| **phase 12 BLOCK 11 → 10** | hard, external | ✔ Direct file overlap on `docs/ops/prometheus-slo-alerts.yaml`. Phase 12 BLOCK 11 is *making that file a verified contract* — correcting selectors, correcting the stale multiprocess caveat, adding the scrape-contract test. Two phases writing one file in one window is a silent failure, not a collaboration |

### 4.3 Where there is deliberately **no** edge, and why

| Pair with no edge | Why |
|---|---|
| **4 ↔ 1/2/3** | BLOCK 4 is a cache-lifetime contract. It shares no file, no CI job and no tripwire with the harness blocks. Making it depend on the harness would delay the phase's second structural block behind a soft, non-load-bearing ordering |
| **8 ↔ 9** | Two management commands, two advisory locks, no shared file. The report sequences them adjacently for narrative reasons. Coupling them would make one nightly job's failure another's |
| **10 ↔ 11** | An alert YAML and a template context key. There is no shared artefact and no shared decision |
| **BLOCK 4 ↔ `gunicorn.conf.py`** | `PERF-011`'s capacity half is **rejected** (the CPU budget is 1.5, so "near the core count" means *fewer* workers than today). **Phase 13 therefore has no `gunicorn.conf.py` edit at all** — and phase 12 BLOCK 12 owns that file |
| **`PERF-002` ↔ anything** | ✔ Merged out to `SRCH-001`. **There is no edge because there is no block.** Phase 13 implements nothing, and its plan-shape and composite-join remediation are recorded as an *addition to `SRCH-001`'s fix set*, to be applied when phase 08's block lands |
| **The legacy `search_vector` removal ↔ anything** | ✔ Routed out (**Q13**). It is a write-amplification win, not a latency win; it needs a migration in **phase 05's number space**; it breaks `test_search_triggers.py`; and the column is also a **phase-08 FTS surface**. It is unowned today, and this plan records that rather than absorbing it |
| **The `?features=` ceiling ↔ anything** | ✔ Routed to **phase 08's open `Q2`** (**Q14**). Phase 13 must not duplicate that gate, and phase 08's BLOCK 1 has not landed, so there is nothing to measure against |

### 4.4 The orders that are unsafe

1. **BLOCK 2 before BLOCK 1.** The re-baseline would be taken against a gate that exits 2 on
   every run and, once repaired the report's way, would report p95 = 0 forever. **This is the
   phase's one non-negotiable edge**, and the consequence of violating it is a number published
   from an instrument that cannot read.
2. **BLOCK 1 with the report's prescribed fix.** ✔ Not an ordering error but an
   ordering-adjacent one: it lands a gate that **cannot fail**. See C-1 and Q1.
3. **BLOCK 5 split into three commits.** ✔ The whole reason the three findings are one change is
   that the inventory must be measured **after** all three. Splitting it produces three
   intermediate inventories and one final number that matches none of them.
4. **BLOCK 12 before BLOCK 11.** Documentation describing a system the phase has not finished
   changing is the phase-12 BLOCK 15 failure mode. The parity-guard-after-the-truth rule applies
   unchanged.
5. **BLOCK 4 with `cache-strategy.md` while phase 08 BLOCK 6 is in flight.** ✔ Two owners of one
   file, and the same file has **two** possible edits (the durable-key contract and the TTL
   invariant). Same commit or strict sequence — never parallel.
6. **BLOCK 10 while phase 12 BLOCK 11 is in flight.** ✔ Two owners of one alert file. If the
   coordinator prefers the parallel path, the fallback is BLOCK 10's option (c): land a reviewed
   fragment, change no file, and record the finding as not-yet-applied.
7. **BLOCK 6 or 8 on a "while we're here" basis.** ✔ `work_mem` (6) and a transaction-shape
   change (8) are both **rejected upstream and not re-litigated here** — one is an OOM risk
   against a 1 GB container, the other is `DB-008`, phase 03's.
8. **Any block that raises `_QUERY_BOUND`.** ✔ Not an ordering error, but the same class: it
   converts a guard into a rubber stamp. **Q7's floor is that the number may only go down, and
   only from a recorded measurement.**
9. **Any block restoring `.ai/audit/13-performance/findings.md`** or editing anything under
   `.ai/audit/`. It is deleted; the validated report is the record (C-6).
10. **Any block adding an `AdvisoryLockId`.** ✔ Next free is `14`, and
    `test_advisory_lock_ids.py` is the tripwire. Phase 13 allocates **none**.

### 4.5 What the DAG does *not* decide

The DAG orders blocks. It does **not** resolve Q1 … Q14. Each is a gate inside a block, recorded
in that block's `extra_context` and in §0.5, and §8.1 checks that a **written** answer exists for
each. **A block whose gate is unanswered does not start, and the Implementor is forbidden from
choosing the option.**

The DAG also does not sequence phase 13 against the other phases. §5 does, from phase 13's side
only. **Phase 13 does not contact, negotiate with, or wait on any other agent** — the coordinator
sequences the cross-phase gates. Two of them are **externally blocking** and the coordinator must
place them: **phase 08 BLOCK 6 → BLOCK 4**, and **phase 12 BLOCK 11 → BLOCK 10**.

---

## 5. Cross-phase coordination

Plans `.ai/plans/01-…` through `.ai/plans/12-production-ops-remediation.md` all exist; phases
**14 and 15 are being planned in parallel** as this plan is written. This section is the boundary
contract and is deliberately **one-directional**: phase 13 states what it owns, what it will not
touch, and where its boundaries lie. **It does not attempt to contact the other agents.** Where
this plan records another phase's state, it records only what it verified in the tree.

### 5.1 What phase 13 already owns and must not re-ship

| Prior work | What it shipped | Consequence for phase 13 |
|---|---|---|
| **Phase 01 `ENT-001`** | ✔ **Shipped.** The `child_exit` guard, `PROMETHEUS_MULTIPROC_DIR` on `web`, its tmpfs, and the `test_compose_contract.py` assertions | ✔ **`PERF-011`'s "sequence after `ENT-001`" constraint is discharged** (C-3). BLOCK 10's alert work is unblocked on that axis. **And the file's multiprocess caveat is therefore stale** (C-4) — which is **phase 12 BLOCK 11's correction, not phase 13's** |
| **Phase 01 `ENT-003`** | ✔ The durable daily marker and `send_alerts` idempotency | BLOCK 9 groups the daily alert loop. **Do not add a second dedupe mechanism** and do not disturb idempotency |
| **Phase 01 `ENT-004`** | ✔ CI lint and typecheck scoped to `src/` | The `locustfile.py` work of BLOCKS 1 and 2 is **outside** `src/` and therefore outside that gate — another reason the load test is a separate path (§1.2) |
| **Phase 02 `CFG-001`** | ✔ `ALLOWED_ENV_VARS` and the `DJANGO_ONESHOT` import gate | **This plan adds no env key.** `test_env_allowlist.py` is untouched and green in every block. If a block appears to need one, that is a report, not an edit |
| **Phase 02 `CFG-002`** | ✔ `ci.yml`'s `deploy-check` env block | BLOCKS 1 and 2 edit the **`load-test` job only**. **Nothing may be appended after `deploy-check:`** — `_deploy_check_section()` slices from that marker to EOF |
| **Phase 03 `DB-004`** | Not yet shipped — `statement_timeout` / `lock_timeout` still absent, live-verified `0 ms` / `0 ms` | ✔ **Phase 13 adds neither.** `VAL-001` (this phase's own finding) makes it a **co-equal P0 with `SRCH-001`**, because the crash-recovery window is WAL-redo-bound and unbounded by the application. **Phase 13 may measure against the chosen value; it may not set it.** BLOCK 12 records that `TestRecomputeRowLockConcurrency`, `test_sweep_archive` and `test_transition_concurrency` hold locks ~1 s and break under a global `lock_timeout` below that |
| **Phase 03 `DB-008`** | Whole-sweep transaction restructuring | **`PERF-013` is cost quantification only.** Phase 03 BLOCK 7 rewrites `archive_sweep` and `recompute_normalized_prices`; BLOCK 12 touches neither |
| **Phase 03 BLOCK 11** | ✔ The **`PERF-` namespace sweep**, and it **forbids other phases from touching it** | See §5.2 item 1 and the reservation table below. **Phase 13 does not rename, retag or clean any of the six collided strings**; it adopts a citation convention instead (§0.1) |
| **Phase 05** | `apps/ads/models.py` and the `ads/migrations` number space | **The legacy `search_vector` + `IX_ads_search_gin` removal is routed OUT of this plan** (**Q13**). It is a write-amplification win, not a latency win; it needs a migration in phase 05's space; and it breaks `test_search_triggers.py`. **This plan ships zero migrations** |
| **Phase 06 BLOCKS 5/7** and **Phase 03 BLOCK 9** | Alert eligibility and delivery state on `alert_query.py` | **A three-way reservation: phase 06, phase 03, phase 13 — and phase 13 claims none.** BLOCK 9's gate **Q11** exists because the function's contract may have changed. **Re-read immediately before editing; stop and report if it has** |
| **Phase 07 `MEDIA-006`** | nginx `limit_req` reducing `media_gate`'s lookup load | **Complement, not a claim.** Phase 07 adds no index and no per-request stat. If phase 13 were to plan an index for `media_gate`, phase 07's `limit_req` may already have relieved it. **This plan plans no index at all** |
| **Phase 08 `SRCH-001`** | Not yet shipped. BLOCK 1 bounds `?features=`; the composite-join remediation is `PERF-002`'s contribution | ✔ **`PERF-002` is merged away and phase 13 implements nothing** (§6.2). Do not re-measure it — the phase-08 handbook's own instruction is *"13 must assume `SRCH-001`'s fix landed, or it will re-measure an 08-owned defect."* **BLOCK 1 has not landed, so there is nothing to measure against.** Do not duplicate phase 08's `?features=` ceiling gate (**Q14**) |
| **Phase 08 BLOCK 6** (`SRCH-007`) | Not yet shipped. The **durable monotonic version-key contract**: `timeout=None`, four writers migrated, the fifth consumer fixed, and `cache-strategy.md` amended in the same commit | ✔ **Phase 08 owns the durable-key contract; phase 13 owns the TTL tuning** (C-5). **BLOCK 4 is externally gated on this block's landing state**, and `cache-strategy.md` is **phase 08 BLOCK 6's sole owner** — same commit or strict sequence, never parallel (§4.4 item 5) |
| **Phase 08 BLOCK 6, planning side** | Its own `Q1` asks *"who owns the cache-version-key lifetime after the 2026-09-28 handbook rewrite?"* and answers itself: the rewritten handbook **block 10** assigns *"a freshness/version token's lifetime against the lifetime of the data it retires"* to phase 13, leaving phase 08 the stale-read half | ✔ **That is this plan's BLOCK 4.** The division of labour is settled: **phase 08 owns the contract, phase 13 owns the relationship between the token's lifetime and the entries it retires** — today `300 s` counter eviction against `300 + 60 = 360 s` entries. ⚠ **The block number is a trap: phase 13 handbook block 10 is "Background and batch work"**, which this plan covers in BLOCKS 8, 9 and 12. **Plan block numbers and handbook block numbers are different namespaces; never cite a bare block number in a commit** |
| **Phase 08 BLOCK 1** | Not yet shipped | `ListingsQueryParams.feature_slugs` is phase 08's. **Phase 13 does not touch it** |
| **Phase 09 BLOCK 10** | Not yet shipped. `media_gate`'s duplicated `AdImage` query | **Phase 13 must assume it landed, or it re-measures an 09-owned defect as a phase-13 finding.** **It has not landed — verify before filing anything about `media_gate`. This plan files nothing about it** |
| **Phase 09** on `apps/core/utils/cache.py` | The cache-failure policy (`cache_get_or_none`, the window helper) | **Phase 13 grades effectiveness; phase 09 owns the policy.** **Phase 13 creates no competing cache-failure helper** |
| **Phase 10** | `test_search_query_count.py` / `test_search_slo.py` as its tripwires; phase 10 BLOCK 14 extracts `build_listings_context()` | ✔ Phase 10 and phase 11 have **explicitly forbidden themselves from making latency or index claims** — which is precisely what phase 13 exists to do. **Phase 13 edits those two files only as an incidental rewrite, in the same commit as the production change, never weakening an assertion, and naming the phase in the commit body** |
| **Phase 11** | The two tripwire files as **"nobody"**; `ci-nightly.yml` (**first** phase to touch it); `ci.yml`'s `test` job; `[tool.pytest.ini_options]` | ✔ BLOCK 3 needs `ci-nightly.yml` for the `profile_queries` job and BLOCKS 1/2 need `ci.yml`'s `load-test` — **disjoint regions, sequential with a re-read.** **Nobody adds a dependency** (no pytest-timeout). Phase 11's ordered test-change schedule says phase 13 *extends* the subprocess shape and does not rewrite phase 02's applicability tests |
| **Phase 12 BLOCK 11** (`OPS-003`) | Not yet landed. Making `docs/ops/prometheus-slo-alerts.yaml` a **verified contract** | ✔ **Direct overlap with `PERF-011`'s observability half.** Phase 12 corrects the selectors, corrects the **stale** multiprocess caveat, and adds the scrape-contract test. **BLOCK 10 is externally gated on it** (§4.2) and **must not restate any of its corrections** |
| **Phase 12 BLOCK 12** (`OPS-012`) | `gunicorn.conf.py` log format | ✔ **Phase 13 has no `gunicorn.conf.py` edit at all** — `PERF-011`'s capacity half is rejected. Phase 12's `child_exit` hook is untouched by phase 13 |
| **Phase 12** on runbooks | Runbook procedures (crash recovery, DB memory budget, 429) | **Phase 13 states parameters; phase 12 writes the procedure.** Phase 13 edits no runbook |
| **Phase 14** | Locale files; the language component of a cache key | ✔ **Phase 13's ONLY user-visible string is BLOCK 7's truncation notice**, and the 2026-10-03 Product Owner ruling makes that string **required, not optional**: the existing notice in `ad_list.html` is reworded, its `ru` and `bs` `msgstr` must be non-empty, and `test_i18n_completeness.py` green. **No `makemessages` regeneration**, and the catalogue is appended to, never regenerated |
| **Phase 15** | The authorization framework | **Out of scope** |

### 5.2 What phase 13 must **not** do, for other phases' sake

1. **Do not touch the six `13-PERF-00N` strings in shipped source.** ✔ **Phase 03 BLOCK 11 owns
   that sweep and forbids other phases from touching it.** Those strings are phase-08/10/11
   deliverables that happen to share a prefix: `test_search_slo.py` (×3),
   `prometheus-slo-alerts.yaml`, `ci.yml`, `Makefile`, `test_lookup_cache_swr.py` (×2),
   `test_search_cache.py`, `test_search_query_count.py`, `cache-strategy.md` (×2),
   `test_cache_key_convention.py` (×2), `test_submenu_swr.py`. **Phase 13's obligation is to not
   make the collision worse** — hence the citation convention in §0.1 — not to clean it.
2. **Do not add `statement_timeout` or `lock_timeout`.** ✔ **Phase 03 `DB-004`'s**, in the
   most-contended settings file after `conftest.py`. Phase 13 may measure against the chosen
   value.
3. **Do not edit `test_search_query_count.py` or `test_search_slo.py` except as an incidental
   rewrite** in the same commit as the production change it describes, never weakening an
   assertion, and naming phases 10 and 11 in the commit body. ✔ Both are tripwires for other
   phases; both are listed as **"nobody"** in phase 11's plan.
4. **Do not allocate, renumber or reorder an `AdvisoryLockId`.** ✔ Next free is `14`; phases
   03/05/06/07/10 all list `apps/core/enums.py` as contended.
5. **Do not edit `src/backend/conftest.py`.** ✔ It is the most contended file in the repository.
   If a block needs a fixture — `PERF-009`'s measurement would — that is a signal to measure on
   the dev stack.
6. **Do not add a pytest dependency, and do not change `testpaths` unless Q2 explicitly answers
   for it.** ✔ Phase 11 holds the test toolchain.
7. **Do not edit `apps/search/services/alert_query.py` without re-reading it.** ✔ Three-way
   reservation (phase 06, phase 03, phase 13-none).
8. **Do not touch `docs/architecture/cache-strategy.md` before phase 08 BLOCK 6 has landed**, and
   never rewrite its durable-key paragraph. ✔ Phase 08 BLOCK 6's sole owner.
9. **Do not touch `apps/ads/models.py`, `ads_search_vector_update` or `setup_search_triggers`.**
   ✔ Phase 05's model surface; phase 08's FTS surface. The legacy `search_vector` removal is
   routed out (**Q13**).
10. **Do not append anything after `deploy-check:` in `ci.yml`, and do not touch the
    `deploy-check` `env:` block.** ✔ Phase 02 owns it, and `_deploy_check_section()` slices to
    EOF.
11. **Do not edit `config/settings/base.py` or `config/settings/test.py`.** ✔ `base.py` is claimed
    by phases 02, 03, 06, 08, 09; `test.py` is under live concurrent edit **and** is phase 11
    BLOCK 5's file. Phase 13's settings surface is **one `CACHES` read**, and that is a read.
12. **Do not restore or edit anything under `.ai/audit/`,** including the deleted
    `.ai/audit/13-performance/findings.md` (C-6).
13. **Do not add a migration or an index.** ✔ This plan ships zero of each. A block that needs one
    is `DB-008`'s, phase 05's, or Q13's business.
14. **Do not make a latency or `EXPLAIN` claim in another phase's file.** If a phase-13
    measurement belongs to another plan's artefact, **record it and route it** (§6.2).

### 5.3 Shared-artefact reservations

The coordinator sequences these. Phase 13's claim is stated so it can be compared; **phase 13
does not negotiate.**

| Artefact | Phase-13 claim | Other claimants | Ordering rule |
|---|---|---|---|
| `src/benchmark/locustfile.py` | **BLOCKS 1 → 2** | Nobody | Sequential; both in place |
| `.github/workflows/ci.yml` | **BLOCKS 1 → 2**, the **`load-test` job only** | Phase 11 BLOCK 2/3 (`test` job, `timeout-minutes`), phase 09 BLOCK 15, phase 02 (`deploy-check` env) | ✔ **Disjoint regions — sequential with an immediate re-read before each edit. Never append after `deploy-check:`. Phase 02's `env:` block is read-only for both** |
| `.github/workflows/ci-nightly.yml` | **BLOCK 3**, a new `query-profile` job | ✔ **Phase 11 BLOCK 2 — "the first phase to touch `ci-nightly.yml`; no other plan claims it"** | **Phase 11 first, then phase 13.** Re-read immediately before editing; append nothing after a phase-11 marker |
| `docs/ops/prometheus-slo-alerts.yaml` | **BLOCK 10** (externally gated) | ✔ **Phase 12 BLOCK 11 (`OPS-003`)** | **Phase 12 first, strictly.** Phase 13 does not restate any phase-12 correction |
| `docs/architecture/cache-strategy.md` | **BLOCK 4**, after phase 08 | ✔ **Phase 08 BLOCK 6, sole owner** | **Same commit or strict sequence — never parallel** |
| `docs/ops/profiling.md` | **BLOCK 12** | Nobody | Last block in the plan |
| `apps/search/views/search.py` | **BLOCKS 6, 7, 11** | Phase 10 BLOCK 14 extracts `build_listings_context()` | **Sequential within phase 13: 6 → 7 → 11.** Phase 10's extraction is outside the phase-13 window; if it lands mid-run, re-read |
| `apps/core/context_processors.py` | **BLOCK 5** | Nobody | One phase-13 owner |
| `apps/trust/templatetags/trust_tags.py` | **BLOCK 5** | Nobody | One phase-13 owner |
| `templates/components/header_catalog.html`, `templates/categories/partials/mega_submenu.html` | **BLOCK 5** | Phase 07 (media templates — different files) | One phase-13 owner, all sites in one commit |
| `apps/search/services/cache.py`, `apps/categories/services/cache.py` | **BLOCK 4** (reads), conditional write under Q5 | ✔ **Phase 08 BLOCK 6** — the writers | **Phase 08 first.** Phase 13's default is read-only under Q5(b) |
| `apps/search/tests/test_search_query_count.py` | **BLOCK 5** (`_QUERY_BOUND`), **BLOCK 6** (matcher, under Q8) | ✔ Phases 08, 10, 11 — all list it as a tripwire | **Incidental rewrite only, in the same commit as the production change. Never weakened. Named in the commit body** |
| `apps/search/tests/test_search_slo.py` | **BLOCK 1** (docstring only) | ✔ Phases 10, 11 | **Incidental rewrite only. No assertion changed** |
| `apps/ads/tests/test_listings_context.py`, `test_ad_detail_queries.py` | **BLOCK 11** (extends, never rewrites) | Phase 10 BLOCK 14 | Extend; never replace |
| `apps/lookups/tests/*`, `test_cache_key_convention.py` (both copies), `test_submenu_swr.py`, `test_search_cache.py` | **BLOCK 4** (reads as tripwires) | Phases 08, 10 | **Read-only for phase 13 unless Q5(c) requires an extension** |
| `apps/core/management/commands/profile_queries.py` | **BLOCK 3** | Nobody | One phase-13 owner |
| `apps/analytics/management/commands/rollup_daily_metrics.py` | **BLOCK 8** | Nobody | One phase-13 owner |
| `apps/search/management/commands/send_alerts.py` | **BLOCK 9** | Phase 01 `ENT-003` (idempotency) | **One phase-13 owner; do not disturb idempotency** |
| `apps/search/services/alert_query.py` | **BLOCK 9** (read + conditional) | ✔ **Phase 06 BLOCKS 5/7, phase 03 BLOCK 9 — three-way** | **Phase 13 claims none. Re-read; stop and report if either landed** |
| `apps/currencies/management/commands/recompute_normalized_prices.py` | **BLOCK 12** (measurement only) | ✔ **Phase 03 `DB-008` BLOCK 7** | **Phase 13 does not change it. Next free migration is phase 05's space** |
| `apps/core/tests/test_sweep_lock_structure.py`, `test_advisory_lock_ids.py` | **Read-only** | Phases 03, 05, 06, 07, 10 | **Never modified by phase 13** |
| `apps/ads/tests/test_search_triggers.py`, `test_setup_search_triggers.py` | **Read-only** | Phase 08 | **Untouched — this is why the legacy `search_vector` removal is out of scope** |
| `apps/core/tests/test_observability.py` | **BLOCK 10** (extend beside `test_metrics_endpoint`) | ✔ **Phase 01 (the multiprocess contract)** | **Do not disturb the multiproc assertions** |
| `config/settings/**` | **None** | Phases 02, 03, 06, 08, 09, 11 | ✔ Phase 13 edits **no** settings file |
| `apps/core/enums.py` | **None** | Phases 03, 05, 06, 07, 10 | ✔ **Phase 13 allocates no lock id** |
| `apps/*/migrations/` | **None** | Phase 05 (`ads`, next `0008_*`) | ✔ **This plan ships no migration** |
| `src/backend/conftest.py` | **None** | Every phase | ✔ Untouchable |
| `pyproject.toml` | **None**, unless Q2 answers explicitly | Phase 11 (`[tool.pytest.ini_options]`) | ✔ **No dependency; `testpaths` only under Q2** |
| `.ai/audit/**` | **None** | Every phase | ✔ **This plan creates, restores or edits nothing here** |
| Locale files | **BLOCK 7** (append-only; **required** since the 2026-10-03 ruling) | Phase 14 | ✔ No `makemessages` regeneration. BLOCK 7's reworded truncation notice needs non-empty `ru` and `bs` `msgstr`; the existing msgid entry is edited in place, never regenerated |

### 5.4 What phase 13 needs from other phases (forward dependencies)

| Need | From | Status |
|---|---|---|
| **The durable version-key contract** (`SRCH-007`, `timeout=None`, the four writers, the fifth consumer) | **Phase 08 BLOCK 6** | 🔴 **Externally blocking BLOCK 4.** Until it lands, the counter's eviction behaviour is about to change underneath any tuning. **Q5 must record its state** |
| **A corrected, contract-backed alert file** | **Phase 12 BLOCK 11** (`OPS-003`) | 🔴 **Externally blocking BLOCK 10.** Two owners of one file. Phase 13 does not negotiate the order |
| The `ci-nightly.yml` region for `profile_queries` | Phase 11 BLOCK 2 | 🟡 **Soft.** Disjoint region; phase 11 is the first to touch the file and re-read is required |
| The `test` job's pytest step and job timeouts | Phase 11 | 🟢 **None.** Phase 13 does not touch that region |
| `SRCH-001`'s `?features=` bound | Phase 08 BLOCK 1 / `Q2` | 🟢 **None.** `PERF-002` is merged out; phase 13 implements nothing and duplicates no gate (**Q14**). **`Q14` was ANSWERED on 2026-10-03 — no hard-coded ceiling; a catalogue invariant plus headroom, enforced by a guard test — so `PERF-002`'s remediation quality is satisfied by phase 08. Phase 13 still implements nothing for it** |
| `media_gate`'s de-duplicated lookup | Phase 09 BLOCK 10 | 🟢 **None.** Phase 13 files nothing about `media_gate` |
| `statement_timeout` / `lock_timeout` | Phase 03 `DB-004` | 🟡 **Measurement only.** Phase 13 measures against whatever is chosen and sets nothing. **BLOCK 12 records that three lock-holding tests break below ~1 s** |
| A production-sized dataset for BLOCKS 8, 9, 12 | A private `postgres:18-alpine` instance | 🟡 **Verification, not implementation.** The plan ships tripwires whether or not the measurement is taken, and records "not measured" when it is not |
| The owner rulings | Owner | **`Q9` — ANSWERED 2026-10-03 (Product Owner, option (a)); BLOCK 7 is unconditional and ships its full deliverable. `Q5` and `Q12` remain open** — those two are the phase's remaining real external dependencies, both recorded as decisions, not tasks |

---

## 6. Out of scope for this plan

Every de-scoping below is **routed**, not dropped. A de-scoped item with no destination is a
re-filed finding.

### 6.1 De-scoped by design (deliberately not done here, with the rationale)

| Item | Why |
|---|---|
| **The legacy `search_vector` column + `IX_ads_search_gin` removal** (**Q13**) | Phase 08 routed it to phase 13 as an "index-grading item", and it is **currently unowned**. It is **not** done here for four reasons: it is a **write-amplification win, not a latency win**; it needs a **migration in phase 05's number space**; it **breaks `test_search_triggers.py` and `test_setup_search_triggers.py`**, which are also phase-08 FTS surfaces; and the column is **dual-claimed** by phase 08's FTS work. **Default ruling: out of scope, and the coordinator must place it.** The item stays visible, not forgotten |
| **Caching the header `cities` list** (`PERF-008`'s larger limb) | The shipped list is **15 rows** (~8 KB, ~0.2 ms). Every headline figure came from 5 015 injected rows. Caching 15 rows is **overengineering** (§0.2.2 rule 3), and the **city-data source is a phase 06/07 decision** — phase 13 would be caching a list whose contents are still being decided. **Routed to phases 06/07 with the measurement attached** |
| **Cold-miss coalescing for the search cache** (`PERF-007`) | ✔ True on the **cold-miss** path only; on the stale-window path — the common case — losers correctly serve stale and only the winner recomputes, so the report's "it is not a stampede guard" is **false there**. The `default`-and-fall-back contract is documented and intentional, and the exposure is bounded by a **3-worker sync** deployment. The implied remedies (a task queue, an async coalescer) are **new infrastructure for a bounded, already-documented behaviour**. **The contract is left as documented; the ruling is recorded, and the finding is dispositioned as accepted-and-unchanged rather than silently dropped** |
| **`work_mem` / `max_connections` tuning** (`PERF-006` fix #3) | **Rejected upstream and not re-litigated.** A per-connection × per-node multiplier against a **1 GB `DB_MEM_LIMIT` that ships to production** — and unnecessary once BLOCK 6's cap-in-SQL lands. The concrete risk is **turning a bounded slow request into an immediate container OOM** |
| **Raising gunicorn `workers`** (`PERF-011`'s capacity half) | **Rejected upstream and not re-litigated.** `web` ships `cpus: ${WEB_CPUS:-1.5}` with **no `.env.*` override**, so "a worker count near the core count" means **1–2 — fewer than today's 3** — on a 74 %-CPU workload. **Phase 13 has no `gunicorn.conf.py` edit at all.** Capacity is a deployment decision, not a remediation-block decision |
| **`statement_timeout` / `lock_timeout`** (`DB-004`) | **Phase 03's**, in the most-contended settings file. This phase's own `VAL-001` finding makes it a **co-equal P0 with `SRCH-001`** — the crash-recovery window is WAL-redo-bound, so the outage is *time-to-kill + redo*, the second term unbounded by the application. **Phase 13 records the priority and measures against the chosen value; it sets nothing.** BLOCK 12 records that three lock-holding tests break under a global bound below ~1 s |
| **Restructuring the sweep transactions** (`DB-008`) | **Phase 03 BLOCK 7's.** `PERF-013` is cost quantification only, and `send_alerts`' immediate-alert write batching is the same territory. **Phase 13 groups a loop; it does not move a transaction boundary** |
| **`prefetch_related("children")` for the header N+1** (`PERF-009`) | **A no-op against `mptt`'s `get_children`** — rejected upstream. The correct instrument is an `Exists` annotation, which is what BLOCK 5 uses. Recording it here so nobody re-proposes it |
| **Restructuring `recompute_normalized_prices`** (`PERF-013`) | **Phase 03's.** ✔ The command is **absent from both `HOURLY_COMMANDS` and `DAILY_COMMANDS`** and runs only on demand, so its transaction shape is a phase-03 decision with real concurrency tests (`TestRecomputeRowLockConcurrency`) guarding it. **BLOCK 12 measures and documents; it does not restructure** |
| **The `?features=` ceiling** (**Q14**) | **Phase 08's `Q2` — ANSWERED 2026-10-03** (no hard-coded ceiling; a catalogue invariant plus headroom, enforced by a guard test). **Phase 13 duplicates no gate** and implements nothing for `PERF-002` |
| **Extending `testpaths`, adding a pytest dependency, or consolidating the tripwire test files** | Phase 11 holds the test toolchain and the ordered test-change schedule. Phase 13 edits `test_search_query_count.py` and `test_search_slo.py` **only as incidental rewrites**, and **only if Q2 explicitly answers for a `testpaths` change** |
| **Any environment tuning to make a benchmark look better** (`WEB_CPUS`, `WEB_MEM_LIMIT`, `DB_CPUS`, `DB_MEM_LIMIT`, `SCHEDULER_CPUS`) | Those variables are **runtime-verified as unset in every `.env.*`**, which is why `PERF-011`'s capacity half is rejected. **Changing them is an env-key change** (phase 02's allowlist) and a capacity decision, and this plan adds **no** env key |
| **A multi-level category fixture in `conftest.py`** | It is the most contended file in the repository, and adding a fixture to it for one measurement is a poor trade. **`PERF-009` is measured on the dev stack** (7 active roots, 205 categories) and the committed tripwire asserts the **shape** — a constant number of child-existence queries — which needs no new fixture |
| **Making the load test part of pytest, or the fast gate part of the load test** | They are **different instruments on different paths** (§1.2). `src/benchmark/` is outside `testpaths`; the p95 gate is enforced by one CI job and nothing else. **Merging them would make a green fast gate look like latency coverage it does not provide** |
| **Correcting `.ai/audit/13-performance/findings.md`** (`VAL-002`) | The file is **deleted from the tree**. The six corrections are recorded in **§0.4 (C-1, C-2, C-6, C-7) and §0.2.4** instead, and **phase 13 creates, restores or edits nothing under `.ai/audit/`** |

### 6.2 Rostered elsewhere, not dropped

| Item | Owner | Note |
|---|---|---|
| `SRCH-001` — bounding `?features=` **and** the composite-join remediation | **Phase 08** | ✔ `PERF-002` is merged away. Phase 13 contributes **two additions** to `SRCH-001`'s fix set: the `COUNT(*)` row-count amplification table, and the single composite `slug__in` + filtered `Count` join that replaces N nested loops with a **constant-shape** plan. **A cap alone leaves a bounded-but-still-quadratic plan — so the join collapse is the half that matters.** **Cross-reference, never merge** |
| `DB-004` — `statement_timeout` / `lock_timeout`, per role | **Phase 03** | Co-equal P0 with `SRCH-001` per `VAL-001`. **Phase 13 adds neither** |
| `DB-008` — whole-sweep transaction restructuring | **Phase 03** | `PERF-013` is cost quantification only |
| The `PERF-` namespace sweep | **Phase 03 BLOCK 11** | ✔ **It owns it and forbids other phases from touching it.** Phase 13 adopts a citation convention instead (§0.1) and touches none of the six strings |
| `03-DB-004` interaction with `PERF-005`'s `alert_query.py` reads | **Phases 06 / 03** | ✔ Three-way reservation. BLOCK 9's gate **Q11** is the re-read |
| `SRCH-007`'s durable monotonic version-key contract | **Phase 08 BLOCK 6** | ✔ **Phase 08 owns the contract; phase 13 owns the TTL relationship.** BLOCK 4 is externally gated on it |
| `OPS-003` — the alert file's selector corrections, the stale multiprocess caveat, the scrape-contract test, the monitoring-stack decision | **Phase 12 BLOCK 11** | ✔ **Direct overlap with `PERF-011`.** BLOCK 10 is sequenced after it and restates none of it |
| `OPS-012` — `gunicorn.conf.py` log format | **Phase 12 BLOCK 12** | Phase 13 has no `gunicorn.conf.py` edit; phase 01's `child_exit` hook is untouched |
| `MEDIA-006` — nginx `limit_req` on `media_gate` | **Phase 07** | **Complement, not a claim.** Phase 13 plans no index for `media_gate` |
| `media_gate`'s duplicated `AdImage` query | **Phase 09 BLOCK 10** | Not landed. **Phase 13 must verify before filing anything about it — and files nothing** |
| The cache-failure policy (`cache_get_or_none`, the window helper) | **Phase 09** | Phase 13 grades effectiveness and **creates no competing helper** |
| The language component of a cache key | **Phase 14** | Phase 13 touches the version token's lifetime, never the key's language composition |
| The `?features=` product ceiling | **Phase 08's `Q2`** | ✔ **Q14** — do not duplicate |
| The authorization framework | **Phase 15** | Out of scope |
| `PERF-009`'s third call site's per-request cost claim | — | ✔ **It is a cached fragment.** If Q6 covers it, its benefit is described as a **cache-miss** improvement. **A per-request claim there would be a false performance claim** (§0.2.3) |

### 6.3 Explicitly forbidden while implementing

1. Touching, renaming, retagging or cleaning any of the **six `13-PERF-00N` strings** in shipped
   source. ✔ **Phase 03 BLOCK 11 owns that sweep and forbids other phases from touching it.**
   Cite new work with the §0.1 convention instead.
2. Adding `statement_timeout`, `lock_timeout`, an `AdvisoryLockId` member, a migration, or an
   index.
3. Raising gunicorn `workers`, or changing `WEB_CPUS` / `WEB_MEM_LIMIT` / `DB_CPUS` /
   `DB_MEM_LIMIT` / `SCHEDULER_CPUS` / `work_mem` / `max_connections`.
4. Using `stats.get("Total", …)` — or any expression that can resolve through
   `EntriesDict.__missing__` — in the p95 hook, or deleting the positive control.
5. **Repairing** the dead `awk` block instead of deleting it.
6. **Weakening or re-scoping** the hot-path FTS `COUNT(*)` ban in `test_search_query_count.py`.
7. **Raising** `_QUERY_BOUND`. It may only go **down**, and only from a recorded measurement.
8. Adding, removing, reshaping or **session-scoping** an `advisory_lock`, or moving
   `select_for_update` out of `recompute_normalized_prices._process_batch`.
9. Editing `test_search_query_count.py` or `test_search_slo.py` except as an **incidental
   rewrite in the same commit as the production change**, and never weakening an assertion.
10. Touching the six `apps/lookups/tests/*` cache-convention tests, `test_submenu_swr.py` or
    `test_search_cache.py` except to extend, never to rewrite.
11. Editing `src/backend/conftest.py`, any `config/settings/**` file, `apps/core/enums.py`, or
    `pyproject.toml` (except `testpaths` under an explicit Q2 answer).
12. Appending anything after `deploy-check:` in `ci.yml`, or editing its `env:` block.
13. Editing `docs/ops/prometheus-slo-alerts.yaml` before phase 12 BLOCK 11 has landed, or
    restating any of its corrections.
14. Editing `docs/architecture/cache-strategy.md` before phase 08 BLOCK 6 has landed, or
    rewriting its durable-key paragraph.
15. Editing `alert_query.py` without re-reading it, or proceeding if phase 06 or phase 03 has
    landed.
16. Citing a bare block number in a commit, a comment or a test docstring. **Plan block numbers
    and handbook block numbers are different namespaces**, and **phase 13's handbook block 10 is
    "Background and batch work"** (C-5).
17. Writing a latency number, a `COUNT(*)` number, or a page-size figure into a commit body
    without the command that produced it. **A single-request timing is a smoke measurement and
    may never be presented as a percentile-SLO result** (§0.2.3, `VAL-003`).
18. Creating, restoring or editing anything under `.ai/audit/`, including the deleted
    `.ai/audit/13-performance/findings.md`.
19. Running a test on the host (`uv run pytest` always fails), using `--override-ini=addopts=`, or
    pointing a measurement at the shared `test_mko_bazuna` database.
20. Running the load test against the shared test stack, or against a production host.
21. `git reset` / `git checkout` / `git restore` / `git stash` / `--amend` / force-push, or
    reverting a file another agent changed. `git add -A` or `git add .`.
22. Writing a test that asserts a line number, a template-string substring, a literal private
    name, or the mere presence of a symbol (§1.5) — or shipping a guard that was never
    **demonstrated failing**.
23. Deleting a shipped source-inspection test to make a block green.
24. `ruff check --fix` over anything other than the files the current block edits; `ruff format`
    (not the project convention).

---

## 7. Per-block risk register

Severity here is **this Planner's assessment of execution risk for the change**, not the
finding's severity. "Blast" covers what else feels the change. "Contention" covers shared files.
"Behaviour" covers observable response changes. "Corpus" covers global or cross-cutting edits.

| Block | Risk | Kind | Likelihood | Impact | Mitigation / detection | Residual |
|---|---|---|---|---|---|---|
| **All** | A block runs with its gate unanswered, or the Implementor silently picks an option | Process | Med | **High** | Every gate is a labelled block in §3 and a row in §0.5, repeated verbatim in the task YAML's `extra_context`; §8.1 checks a **written** answer exists for each | Low |
| **All** | A perf block ships with "feels faster" and no proof | Quality | **High** | **High** | The §3 measurement contract — every block declares **(M)** measured before/after, **(T)** tripwire, or **(M+T)**, in its `acceptance_criteria`. **A block that can state neither does not ship** | Low |
| **All** | A guard is added and never observed failing, reproducing `VAL-003` in the guard that exists to close it | Quality | **High** | **High** | §1.5; **every** new guard's acceptance criteria include "and that failure is demonstrated before the commit" | Low |
| **All** | A number from the report is repeated as a phase-13 result — most likely the 510 ms single sample | Correctness | **High** | **High** | §0.2.3 row 5 and `VAL-003`; the "no latency claim" constraint is in BLOCKS 1, 2 and 6; §6.3 item 17 | Low |
| **All** | A performance change alters semantics and is described as a speedup | **Correctness** | Med | **High** | §0.2.2 rule 1; every ordering/display/freshness change is §6 or a gate (`Q9`, now ruled 2026-10-03); `test_search_query_count`'s `COUNT(*)` ban and the SLO tripwire are the detectors | Low |
| **All** | The Implementor works from the **report's** file list and follows a quoted artefact that does not exist | Process | **High** | **High** | ✔ C-1, C-2, C-6, C-7 and §0.2.4's re-verification table. Every block's `extra_context` names the tree-correct target; the report is evidence, not instruction | Low |
| **All** | A `13-PERF-00N` citation is written into a new comment and re-points a reader to a different finding | Correctness | Med | Med | §0.1's mandatory convention; §6.3 item 1. **The six collided strings are phase 03 BLOCK 11's to sweep** | Med — accepted, by reservation |
| **All** | A red gate is captured while another phase agent runs and a teardown race is reported as a product defect | Process | **High** | Med | Concurrent runs collide on one `test_mko_bazuna`. Re-run serially before reporting. The symptom is `test_mko_bazuna does not exist` / `relation "..." does not exist` | Low |
| **All** | A phase-02/03/08/09/11-owned file is edited on a stale read | Contention | **High** | Med | Re-read immediately before editing; stop and report on a concurrent change; never stage by directory. Normal for `config/settings/**`, `apps/core/enums.py`, `conftest.py`, `pyproject.toml`, `ci-nightly.yml`, `alert_query.py` | Med — accepted |
| **All** | A blanket `ruff check --fix src/` reorders imports another phase's uncommitted work depends on | Process | Med | Med | `[tool.ruff] fix = false` is set deliberately; §6.3 item 24 scopes `--fix` to the block's own files | Low |
| **1** | **The report's prescribed fix lands** — `stats.get("Total", …)` returns 0 and the gate is **permanently green** | **Correctness** | **High** if followed | **High** | ✔ C-1; constraint 1; **a test that fails if any `__missing__`-resolving expression reappears**; the empty-`RequestStats` control arm | Very low |
| **1** | The hook still raises `TypeError` because the correct `get_response_time_percentile` call differs in the installed locust | Correctness | Med | **High** | The control test is written against the **installed** API in the image; the research step under Q1 is a runtime probe, not a docs read | Low |
| **1** | A CI-step assertion parses a second time and breaks on a locust format change | Correctness | Med | Med | Q2's floor: **one** parser, a non-empty assertion. A second parser is §6.3 item 5's exact failure | Low |
| **1** | The first green run is red on latency and is "fixed" by raising the threshold | Behaviour | **High** | **High** | Constraint 3 pins the constant; constraint 7 forbids a latency claim; the commit body must say the red is the intended discovery | Low |
| **2** | A slug in the load-test URL does not exist in the shipped catalogue and the job goes permanently red | Behaviour | Med | Med | Constraint 1; the slugs are verified against `categories.yaml` before the edit; option (c) (runtime resolution) is **rejected by Q3** precisely because it hides this | Low |
| **2** | A non-zero failure tolerance is chosen and averages away a real regression | Correctness | Med | **High** | Q3's floor is a **0 %** assertion; the guard is demonstrated failing | Very low |
| **3** | The threshold axis becomes a match count and no environment can satisfy it, so the tool is unusable | Correctness | Med | Med | Q4; the command must **say** which axis was unmet and exit non-zero either way, so an unsatisfiable axis is loud rather than silent | Low |
| **3** | The nightly job's seed volume blows the nightly budget or times out | **Blast** | Med | Med | Constraint 4: budget it, nightly only, never a PR workflow; the job's `timeout-minutes` is stated in the commit body | Low |
| **3** | BLOCK 3 appends to `ci-nightly.yml` after a phase-11 marker | Correctness | Med | Med | §5.3: **phase 11 is first to touch that file**; immediate re-read; constraint 4 | Low |
| **4** | **The TTL is retuned against a counter that phase 08 is about to make durable** | **Correctness** | **High** without the gate | **High** | The external gate on phase 08 BLOCK 6; Q5 must record the landing state; the invariant is asserted against **settings values**, not a comment | Low |
| **4** | `lock_ttl < stale_ttl < ttl` is broken by a retune, and the SWR tripwires go red for an unrelated reason | Correctness | Med | Med | Constraint 4; the three cache test modules are named in `tests_to_run` | Low |
| **4** | `cache-strategy.md` is edited in parallel with phase 08's block | **Contention** | Med | **High** | §5.3: same commit or strict sequence; §6.3 item 14; §4.4 item 5 | Low |
| **5** | **`_QUERY_BOUND` is raised, or set to the unmeasured "~32" from the shipped comment** | **Correctness** | Med | **High** | Q7; constraint 3 — the bound may only go **down**, and only from a recorded measurement; if the measurement cannot be taken, **the bound does not change** | Very low |
| **5** | The header's `has_children` annotation returns a wrong answer for a node whose children are all inactive, changing what the menu renders | **Behaviour** | Med | Med | The tripwire asserts the rendered menu's structure, not the annotation's value; the predicate's own filter is named in the commit body | Low |
| **5** | The `mega_submenu` change is described as a per-request win when the fragment is cached | Correctness | Med | Med | Constraint 5; the commit body must call it a **cache-miss** improvement | Low |
| **5** | The trust-badge fix breaks a caller that genuinely does not prefetch | **Behaviour** | Low | Med | Constraint: **the unprefetched `.get()` fallback stays**; the test asserts zero extra queries in **both** the prefetched and unprefetched cases | Very low |
| **6** | The `[:1000]` plan change stops the hot-path `COUNT(*)` ban's matcher from firing, and the tripwire becomes inert | **Correctness** | Med | **High** | Q8, **resolved by running the test, not by reasoning**; constraint 4 re-points the matcher **to the same intent** and explains it | Low |
| **6** | Slicing the `Case`/`When` arms to the page changes the rendered order | **Behaviour** | Med | **High** | Constraint 2: a multi-page ordering test, demonstrated against the pre-change ordering. **Changing ordering is a semantics change, not a performance change** | Low |
| **6** | A latency figure is invented to "prove" the block | Quality | Med | Med | Constraint 3: the measurement is the compiled statement's length and bind count, and needs no database. **A latency number here is fabrication** | Very low |
| **7** | ~~The owner is not consulted and the displayed count changes by default~~ — **CLOSED 2026-10-03** | **Behaviour** | **CLOSED** | — | The owner was consulted and ruled on 2026-10-03: option (a). The block is no longer `conditional`, there is no reduced deliverable, and a no-code commit is a defect. **The row is retained, not deleted, so the closure is visible** | **Closed** |
| **7** | The truncated branch renders a cached, remembered or previously-computed total instead of the capped value — i.e. the true total is claimed when it cannot be computed | **Behaviour** | Low | **High** | The ruling's binding sub-rule is stated in the block, in constraint 4 and in the task's `extra_context`; the rendered-page test asserts the truncated value is **exactly** `SEARCH_CACHE_MAX_HITS + 1` | Low |
| **7** | The truncation notice's wording changes and a locale is left with an empty `msgstr` | Correctness | Low | Med | Constraint 2: `ru` and `bs` non-empty, `test_i18n_completeness` green, **append, never regenerate** | Very low |
| **8** | `update_conflicts=True` names a `unique_fields` that does not match the real constraint, and the command **raises at 3 a.m.**, nightly, unnoticed | **Correctness** | Med | **High** | Q10; constraint 3 — the constraint's name and its verification site are recorded; the test runs the rollup **twice** and asserts an in-place update rather than a duplicate or a silent drop | Med — accepted, by gate |
| **8** | The lock is moved, session-scoped, or duplicated | Correctness | Low | **High** | Constraint 1; `test_sweep_lock_structure` asserts exactly one, `in_atomic_block is True`, **`session is False`**; phase 13 allocates no lock id | Very low |
| **8** | The report's "305 s → a few seconds" is repeated as a promise | Quality | **High** | Med | Constraint 5 and the acceptance criteria explicitly forbid it; the before/after is a **measured** statement count | Low |
| **9** | Grouping applies the structural filters **once per group**, so two saved searches silently share results | **Correctness** | Med | **High** | Constraint 3 and the tripwire: two searches sharing a query but differing in a structural filter must receive different ads. **This is the block's sharpest edge** | Low |
| **9** | `alert_query.py` has changed under a phase-06/03 landing and the grouping is written against a stale contract | **Contention** | Med | **High** | Q11; constraint 2 — **stop and report**, do not assume | Low |
| **9** | The group is treated as one cap, so a digest silently widens beyond 10 ads | **Correctness** | Med | Med | Constraint 3: `_DIGEST_AD_LIMIT` stays **per-search**; digest composition must be byte-identical for the same data | Low |
| **10** | **Two phases write `prometheus-slo-alerts.yaml` in one window** | **Contention** | Med | **High** | The external gate on phase 12 BLOCK 11; §4.2 and §6.3 item 13; constraint 2 forbids restating phase 12's corrections. The fallback is option (c): land a reviewed fragment, change no file | Low |
| **10** | A new selector names a series that does not exist, and the alert is dead on arrival | **Correctness** | Med | **High** | Constraint 3: every selector must resolve against a **rendered `/metrics`**, and the scrape-contract test must turn red on a dead selector — **demonstrated** | Low |
| **10** | A new rule is built on `cache_hit_rate_slo`, which reads Redis keyspace hits and is ~100 % by construction | **Correctness** | Low | **High** | Constraint 4: **no new rule may reference it**; phase 12 owns the selector correction | Very low |
| **11** | Removing the view's `cities` key blanks the header dropdown | **Behaviour** | Low | Med | The test asserts the city list **still renders**, not that the key is absent; option (b) — removing the header's key — is rejected because the header runs on pages with no `search()` context | Very low |
| **11** | A 5 015-row figure is quoted into a comment, reproducing the finding's own exaggeration | Quality | Med | Med | Constraint 3; §6.3 item 17 | Very low |
| **12** | Documentation is corrected while BLOCKS 1–11 are still landing, and encodes a system that no longer exists | Process | **High** if reordered | Med | The **11 → 12** hard edge (§4.2). Same rule as phase 12's BLOCK 14 → 15: truth first, then any guard | Very low |
| **12** | `recompute_normalized_prices` is "improved" and its two lock tests start failing | **Correctness** | Med | **High** | Constraint 1: measurement only; `test_recompute_command`'s source inspection and `TestRecomputeRowLockConcurrency` are named in `tests_to_run` and must stay green | Very low |
| **12** | A `statement_timeout` proposal is smuggled into the documentation as a recommendation | Process | Med | Med | Constraint 2: it may be **referenced**; it may not be implemented, and the three ~1 s lock-holding tests are recorded as the reason phase 03 must choose per-role | Low |

---

## 8. Definition of done for the whole plan

Phase 13 is complete when **all** of the following hold.

### 8.1 Scope

- [ ] All **15** finding-units have a recorded disposition: **13 implemented** (11 unchanged, 1
      gated — `PERF-011`'s observability half under **Q12**, which the 2026-10-03 round did not
      reach), **1 merged and remediated elsewhere** (`PERF-002` → `SRCH-001`, phase 08), **0 rejected**,
      **0 dropped without a destination**, plus the `SRCH-007` TTL limb implemented in BLOCK 4
      and `PERF-007` dispositioned as accepted-and-unchanged (§6.1).
      **`PERF-006` #2 is no longer in the gated count — `Q9` was answered on 2026-10-03.**
- [ ] Every gated block (**1, 2, 3, 4, 5, 6, 8, 9, 10**) has a **written** answer for each of
      its open questions, naming the option chosen and the consequences accepted. **Silence is
      not an acceptable outcome for any of them.** **BLOCK 7 has no open question: its gate was
      answered by the Product Owner on 2026-10-03 and it ships unconditionally.**
- [ ] Each of **Q1 … Q14** is either answered with a record or explicitly re-routed with a named
      destination. **Q1, Q2, Q3, Q4, Q6, Q7, Q8, Q10, Q11** are Planner/Researcher rulings ·
      **Q9 is answered** (Product Owner, 2026-10-03, option (a)) · **Q5, Q12** remain open
      owner/coordinator decisions · **Q13, Q14** are routed with a stated default (`Q13` → out of
      scope, the coordinator must place the legacy `search_vector` removal; `Q14` → phase 08's
      `Q2`, **answered 2026-10-03**).
- [ ] **Every commit body that cites a finding uses the §0.1 convention** —
      `PERF-0NN (validated 2026-09)`. **No bare `13-PERF-00N` was added**, and **none of the six
      shipped collided strings was touched** (phase 03 BLOCK 11's sweep).
- [ ] `PERF-002` was **not** re-measured, re-filed or partially remediated, and its two
      contributions — the row-count amplification evidence and the composite-join remediation —
      are recorded as **additions to `SRCH-001`'s fix set**.
- [ ] The **`ENT-001` precondition was used, not re-asserted**: `PERF-011` landed without
      re-checking a dependency that had already shipped, and no second metrics-variable control
      was created.
- [ ] `PERF-011`'s **capacity half was not implemented**, and no `gunicorn.conf.py` edit exists
      in this plan's history.
- [ ] The `PERF-009` **third call site** was handled under Q6, and Q6's answer is recorded in the
      commit body **and** in `test_listings_context`'s docstring.
- [ ] The `PERF-008` change targeted the **`cities` key**, not the non-existent
      `save_search_cities`.
- [ ] Every de-scoping in §6 has a named destination or a stated rationale.

### 8.2 Gates — all green

- [ ] `uv run ruff check src/` → exit 0.
- [ ] `uv run basedpyright src/` → **0 errors**.
- [ ] `.\Makefile.ps1 test` → fast gate green (`seed` marker skipped), run **after every block**.
- [ ] `makemigrations --check` → **no changes**. **This plan ships no migration and no index.**
- [ ] The cache-key convention suite is green —
      `test_search_cache.py`, `apps/lookups/tests`, `test_submenu_swr.py`,
      `test_cache_key_convention.py` (both copies) — **and was run before BLOCK 1 as well as
      after** (§0.2.3 row 10: this audit ran no pytest).
- [ ] No env key was added; `test_env_allowlist.py` is **untouched and green**.
- [ ] No locale file was regenerated. **BLOCK 7 DID change a user-visible string** — the
      truncation notice's wording is required by the 2026-10-03 ruling — so
      `test_i18n_completeness.py` is green and the `ru` and `bs` `msgstr` values are non-empty.
- [ ] **The load test was run at least once end-to-end against the dev stack** after BLOCK 2, and
      its failure rate and p95 are recorded — **never against the shared test stack or a
      production host** (§1.2).
- [ ] Every red-gate observation was **re-run serially** before being reported as a defect.
- [ ] **Every guard this plan added or changed was demonstrated failing** at least once, and the
      demonstration is recorded in the commit body.
- [ ] `git status --short .ai` shows **no new modifications** beyond the pre-existing
      `.ai/audit/**` deletions and this plan's own file.
- [ ] No commit was made without an explicit user request; no `git reset`, `git checkout`,
      `git restore` or `git stash` was run at any point; no compose stack was started, stopped or
      modified outside the commands in §1.1.

### 8.3 Per-finding behavioural confirmation

- [ ] **`PERF-001`** — the hook reads `stats.total`; no expression in it can resolve through
      `EntriesDict.__missing__`, and a test fails if one is reintroduced; the inert `awk` block is
      gone; the control is **demonstrated both ways** (a populated `RequestStats` yields a
      non-zero p95, an empty one fails loudly); `P95_SLO_MS` is unchanged or every module
      asserting it changed in the same commit; **no latency number is in the commit body**.
- [ ] **`PERF-002`** — see §8.1. Phase 13 implements nothing and measured nothing.
- [ ] **`PERF-003`** — the second run updates in place, with no duplicates and no silently
      dropped update; exactly one advisory lock, `in_atomic_block is True`, **`session is
      False`**; the constraint's name and verification site are recorded; the before/after
      statement counts are recorded with the environment named; **any duration is measured with
      its command or marked "not measured"**; the report's "a few seconds" is not repeated; no
      migration.
- [ ] **`PERF-004`** — the prefetch branch is genuinely exercised; the pre-fix `.get()` fallback
      no longer fires on a prefetched queryset (**demonstrated**); the unprefetched fallback
      still works; the false comment is gone; zero extra queries in both cases.
- [ ] **`PERF-005`** — digest composition is byte-identical before and after for the same data
      (**demonstrated**); two saved searches sharing a query but differing in a structural filter
      receive different ads; the FTS evaluation count equals the distinct-pair count and is
      asserted; `alert_query.py`'s reservation state is recorded.
- [ ] **`PERF-006`** — the at/over-cap path issues no second FTS evaluation; the hot-path
      `COUNT(*)` ban is **byte-identical or re-pointed to the same intent with the change
      explained**; `results_truncated` and `total_count` are unchanged for every non-truncated
      case; **#2 shipped under the 2026-10-03 Product Owner ruling (option (a)) — the truncated
      total is exactly `SEARCH_CACHE_MAX_HITS + 1`, no true total is claimed when it cannot be
      computed, the notice renders iff truncated, and the new wording has non-empty `ru` and `bs`
      `msgstr`.**
- [ ] **`PERF-007`** — dispositioned as **accepted-and-unchanged** with the rationale recorded
      (§6.1). No queue, no coalescer, no lock change.
- [ ] **`PERF-008`** — the city list renders completely on a search response; the `cities` query
      appears **exactly once**; no other context key changed; no cache, settings key or env key;
      **no figure from the 5 015-row scenario anywhere**.
- [ ] **`PERF-009`** — all three sites are handled per Q6; the per-root child-existence count is
      **demonstrated failing** before the fix and is a constant after; no fixture was added to
      `conftest.py`; if the `mega_submenu` site was covered, its benefit is described as a
      **cache-miss** improvement.
- [ ] **`PERF-010`** — the compiled statement's length and bind count are recorded before and
      after, and the after figure scales with `per_page`; the rendered ad-id order across pages is
      **byte-identical**; **no latency number exists anywhere in the commit**.
- [ ] **`PERF-011`** — every selector in the file resolves against a rendered `/metrics`, and a
      deliberately dead selector turns the guard red (**demonstrated**); **no new rule references
      `cache_hit_rate_slo`**; phase 12 BLOCK 11's landing state is recorded and **none of its
      corrections is restated**; **no gunicorn, compose, env or allowlist change**; if phase 12
      declined a monitoring stack, the commit says the rules have no consumer and **does not
      claim coverage**.
- [ ] **`PERF-012`** — both browse journeys return 200 and the failure-rate guard was
      **demonstrated failing**; `profile_queries` **exits non-zero** below its threshold and the
      output cannot be read as a measurement that happened; above the threshold it exits 0 and
      detects a real Seq Scan; no literal id remains; the nightly job is in `ci-nightly.yml` only.
- [ ] **`PERF-013`** — the command is **byte-identical**; its cost is recorded with the exact
      command that produced it, and "runs on demand only" is stated;
      `test_recompute_command` and `test_edit_views_locking` are green and untouched.
- [ ] **`PERF-014`** — `_QUERY_BOUND` is **lower than or equal to** its previous value, equals the
      measured count plus recorded headroom, and the commit body carries the command that
      produced it; the false `images` sentence is corrected; the `~32-query base` was **not**
      published as a result.
- [ ] **`PERF-015`** — the documentation names both tools and states which one `make profile`
      runs; the false `make up` claim is corrected; the "best signal" wording states what the tool
      can and cannot tell you, including the skip path; the shipped threshold flag and the
      non-zero exit on skip are documented; **no commit body contains an `EXPLAIN` plan the
      recorded command cannot reproduce**.
- [ ] **`SRCH-007` TTL limb** — phase 08 BLOCK 6's landing state is recorded; the inequality is
      asserted from **settings values** and the guard was **demonstrated failing** with the
      relationship inverted; `lock_ttl < stale_ttl < ttl` still holds; no new settings or env key.

### 8.4 Cross-phase integrity

- [ ] **None of the six shipped `13-PERF-00N` strings was touched** (phase 03 BLOCK 11's sweep),
      and every new citation uses the §0.1 convention.
- [ ] `docs/ops/prometheus-slo-alerts.yaml` was not edited before phase 12 BLOCK 11 landed, and
      none of its corrections was restated.
- [ ] `docs/architecture/cache-strategy.md` was not edited before phase 08 BLOCK 6 landed, and its
      durable-key paragraph is intact.
- [ ] `test_search_query_count.py` and `test_search_slo.py` were edited **only** as incidental
      rewrites in the same commit as the production change, **no assertion was weakened**, and
      the owning phases are named in the commit body.
- [ ] The six cache-convention tests, `test_submenu_swr.py` and `test_search_cache.py` were
      **extended, never rewritten**.
- [ ] `test_sweep_lock_structure.py`, `test_advisory_lock_ids.py`, `test_search_triggers.py` and
      `test_compose_contract.py` are **untouched and green**.
- [ ] No `AdvisoryLockId` was allocated, renumbered or reordered; no settings file, no
      `conftest.py`, no `pyproject.toml` (except `testpaths` under an explicit Q2 answer) and no
      `apps/core/enums.py` was edited.
- [ ] `alert_query.py` was re-read immediately before any edit, and the reservation state was
      reported.
- [ ] No file under `.ai/audit/` was created, restored or edited.
- [ ] `git log` shows **twelve** phase-13 commits, one per block, each explicitly staged, with the
      `{type}({scope}): {description}` form and a §0.1-conformant citation.

### 8.5 Project conventions

- [ ] English only; no `print()` anywhere; logging via `logger` with lazy `%s` and no ad content
      or un-sanitized query text.
- [ ] Fixed values via `StrEnum` / `Enum`; no plain strings, dicts or lists used as constants.
- [ ] No new abstraction without a justification in the commit body against
      §0.2.2 rule 3; every accepted remediation reuses a shipped primitive.
- [ ] No schema change; no migration; no index.
- [ ] i18n: every user-visible string wrapped; `ru` and `bs` `msgstr` non-empty; the catalogue
      appended to, never regenerated.
- [ ] Docs in `docs/` are in sync with what the code now does.
- [ ] Production code is king: the **one** pre-authorised test change (BLOCK 5's `_QUERY_BOUND`)
      invoked §0.2.2 rule 2 by name in its commit body and followed the required order — **fix
      the defect → measure → re-derive → change the test**.
- [ ] No line number was used as a task target; every target is a file plus a semantic anchor.
- [ ] Ruff and basedpyright clean on every file the plan touched; `--fix` scoped to those files.

### 8.6 Deliverables

- [ ] Twelve commits, one per block, in the §4.1 order, each independently reviewable and each
      independently revertible.
- [ ] A recorded **before/after** for every block that claims one, with the exact command, the
      environment it ran in, and both numbers — or an explicit **"not measured"** with the reason.
- [ ] A **written answer** for every gate, naming the option and the consequences accepted.
- [ ] This plan file, and **no other `.ai/` modification**.

Phase 13 is done when the p95 gate can fail, the load test measures a site that exists, the
profiler cannot report a measurement it did not take, the header's query count is a constant
rather than a per-root product, the search view no longer re-runs the FTS filter to count, and
every background and background-adjacent path has been either fixed, measured, or recorded as
deliberately unchanged — with no correctness traded for speed anywhere in the sequence.
