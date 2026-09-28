# Phase 13 — Performance: Validated Findings

> Self-contained validation report. Every claim was re-derived from the working
> tree and, where a claim was runtime-dependent, from a fresh probe. **No source
> file was modified.** The reader needs nothing beyond this document.

**Under audit:** `.ai/audit/13-performance/findings.md` (15 findings, prefix `PERF-`)
**Validator scope:** findings only (`problems_only = true`)

**Verification environment.** No code, config, or test was changed. All runtime work
ran in throwaway containers built from the project's own `mko-bazuna-test-test:latest`
image (which is what CI installs from `uv.lock`) and from `postgres:18-alpine`:

- A short-lived `docker run --rm` container executed the **real**
  `src/benchmark/locustfile.py` against an instrumented HTTP server, producing a
  genuine `_stats.csv` and a genuine process exit code. Auto-removed.
- One isolated `postgres:18-alpine` container (name `perfval-pg`, 700 MB limit, own
  port, disposable) was used to separate *time-to-backend-kill* from
  *crash-recovery time*. **Destroyed**; `docker ps -a` shows no residue.
- The shared `mko-bazuna-test-db-1` instance was **never written to**. The phantom
  `mko_bazuna` database was not touched. No probe artefact remains in `.ai/tmp/`
  (verified: `Test-Path .ai/tmp/perfval → False`).

**What this validation found that the auditor did not.** The gating finding's
conclusion is **inverted**: the auditor reports a gate that always passes; the
actual defect is a gate that always *throws* — plus a shell half that can never
pass. This changes the severity from CRITICAL to HIGH and changes the fix
completely. Six further code quotations, file paths and function names in the
source report **do not exist in the repository**; none of them changes a verdict,
but all of them must be corrected before the report is used as a repair source
(VAL-002).

---

## Validation Verdict Table

| ID | Title (short) | Auditor sev. | Verdict | Validated sev. | One-line justification |
|----|---------------|--------------|---------|----------------|------------------------|
| PERF-001 | CI p95 gate: `awk` reads the wrong CSV column and matches no row | CRITICAL | **ADJUSTED** (conclusion inverted, new defect found) | **HIGH** | The `awk` half is inert (reproduced: `ACTUAL_P95=[]`), but the report's own line 91 — and my reproduction — show the **effective** gate is the `_assert_p95` hook. That hook is *itself* broken: `StatsEntry.percentile()` takes no argument in locust 2.46.6, so it raises `TypeError` on **every** run and the CI step exits **2**. The gate is broken in both directions; regressions are not silent, so CRITICAL is wrong. |
| PERF-002 | `?features=` is a *memory* blowup that SIGKILLs the backend | HIGH | **MERGED** → `SRCH-001` | **CRITICAL** (as SRCH-001) | Same defect, same code path, same failure mode, already adjudicated at CRITICAL by phase 08 with a 20→1.31 s / 40→7.88 s / 60→19.90 s → `signal 9` reproduction on an isolated PG 18. Phase 13's plan-shape and row-count grading is genuine **new supporting evidence** and is retained on SRCH-001; its composite-join remediation is a valuable addition to SRCH-001's fix set. |
| PERF-003 | `rollup_daily_metrics`: ~120 000 SQL in one 305 s transaction | HIGH | **ADJUSTED** (attribution corrected) | **HIGH** | The N+1 upsert loop, the single `transaction.atomic()`, the advisory lock held for the whole run, and the drop-in `bulk_create(update_conflicts=True)` fix are all verified — `DailyAdMetrics` really does carry `uq_daily_ad_metrics_ad_date`. But the claimed *cause* ("99.97 % … pure per-statement overhead, ~2.5 ms/row") is unsupported and the "→ a few seconds" projection is not defensible. |
| PERF-004 | `render_trust_badge` prefetch check can never fire → one failing `SELECT` per card | HIGH | **ADJUSTED** | **MEDIUM** | Mechanism fully confirmed — reverse-`OneToOne` prefetch lands in the descriptor cache, and `RelatedObjectDoesNotExist` subclasses `AttributeError` so `getattr(..., None)` swallows it and the `.get()` fallback fires. But the cost is ~24 index-backed `SELECT`s **only when the trust row is absent**, ≈5–10 ms on a ~420 ms page, on a path that already prefetches correctly. Its second leg rests on a quote that does not exist (VAL-002). |
| PERF-005 | `send_alerts` runs one FTS query per saved search in one lock-held transaction | HIGH | **ADJUSTED** | **MEDIUM** | Structure confirmed verbatim. But 40 searches → 7.6 s, 1 000 → ~190 s, against `SCHEDULER_COMMAND_TIMEOUT = 1 800 s` on a `SCHEDULER_CPUS=0.5` container: linear and bounded, not monopolising. The "secondary cost" is **misattributed** to this path. |
| PERF-006 | ≥1 000 matches → the search cache recomputes the count; warm search is 510 ms | HIGH | **ADJUSTED** (and fix #3 rejected) | **MEDIUM** | The count-bypass defect is confirmed exactly as described. The HIGH argument ("breaches the 500 ms p95 SLO") rests on **one** sample at `DEBUG=1` on synthetic data — the same single-sample fallacy the report criticises in PERF-012c (VAL-003). The `work_mem` proposal is **rejected as written**: it is a per-connection × per-node multiplier against a 1 GB DB container. |
| PERF-007 | Single-flight lock gives no cold-miss protection; all losers run the FTS query | MEDIUM | **ADJUSTED** (narrowed) | **LOW** | True on the **cold-miss** path only. On the stale-window path — the common case — losers correctly serve stale and only the winner recomputes, so "it is not a stampede guard; it is a duplicate-write guard" is false there. The `default`-and-fall-back contract is documented and intentional. |
| PERF-008 | Header materialises the whole `cities` table into every page | MEDIUM | **ADJUSTED** (ROI gated) | **MEDIUM** | Design property confirmed at three sites; the shipped `cities.json` is exactly **15** records, so today's cost is ~8 KB / ~0.2 ms. Every figure is synthetic (5 015 injected). Only the **duplicate** `save_search_cities` has positive ROI now. |
| PERF-009 | 12–13 `cat.get_children.exists()` per page | MEDIUM | **ADJUSTED** (remediation corrected) | **MEDIUM** | N+1 confirmed: exactly two call sites, `header_catalog.html:108` and `:199`, one indexed `SELECT 1 … LIMIT 1` per **non-leaf root** per site — 7 roots in the shipped `categories.yaml` (234 slugs) → up to 14, consistent with the measured 12–13. **The recommended one-line fix does not work** — see the finding. |
| PERF-010 | Cache-hit restore sends 35 KB / 1 000 `CASE` arms / 3 003 binds per page view | MEDIUM | **CONFIRMED** | **MEDIUM** | `search.py:138-144` restores rank with a positional `Case/When` over the *whole* cached id list; statement size and bind count scale with `SEARCH_CACHE_MAX_HITS`, not with page size, so the shape is volume-independent. The page-slice fix is right and trivial. |
| PERF-011 | 3 sync workers cap the tier at 3 in-flight requests; SLO alerts cover only `/search/` | MEDIUM | **ADJUSTED + SPLIT** (capacity half **rejected**) | **MEDIUM** (observability only) | The alert-scope gap is real and free to close. The capacity half is **rejected**: `web` ships with `cpus: ${WEB_CPUS:-1.5}` / `mem_limit: ${WEB_MEM_LIMIT:-512m}` and neither variable is set in any `.env.*`, so "a worker count near the core count" means 1–2 — *fewer* than today, on a 74 %-CPU workload. |
| PERF-012 | Load test 404s on 33 % of traffic; `profile_queries` unrunnable and off-CI | MEDIUM | **CONFIRMED** (two mechanism corrections) | **MEDIUM** | `/c/electronics` has no route; `electronics` and `phones` are real slugs; weight 3/9. `SEED_SCALE_MIN_ROWS = 10 000` and the assertion is skipped below it — but there is no `_scale_dataset()` and the command does not exit early; it prints a misleading green. `test_search_slo.py` is a 60-row, single-sample, p99-constant assertion. |
| PERF-013 | `recompute_normalized_prices`: 125 SQL / 3.0 s / 120 `FOR UPDATE` batches | LOW | **CONFIRMED** | **LOW** | Structure verified, `.only()` projection present, genuinely **absent** from `HOURLY_COMMANDS` and `DAILY_COMMANDS` — it runs only on demand. Correctly scoped as cost quantification for `DB-008`, and correctly sequenced last. |
| PERF-014 | N+1 guard widened to 100 to accommodate the N+1; rationale no longer true | LOW | **ADJUSTED** (central charge unsupported) | **LOW** | The comment the finding quotes **does not exist**. The real comment (`test_search_query_count.py:40-64`) names both N+1s, states the measured value, and prescribes "tighten toward the ~32-query base" once they are fixed — a transparent TODO, not a rationalisation. Only the `images` sentence is genuinely false. |
| PERF-015 | `docs/ops/profiling.md` describes a tool that cannot run | LOW | **ADJUSTED** (claim 1 refuted) | **LOW** | `make profile` runs `scripts/profile_search.py` (cProfile), **not** `profile_queries`; the doc documents them as two tools and correctly states the 10 k skip at `:97`. What survives is real: `_build_queries()` omits the production-path shapes, and the threshold is a table-size axis while the FTS cost axis is match count. |

**Severity movement:** 1 CRITICAL · 5 HIGH · 6 MEDIUM · 3 LOW
→ **0 CRITICAL · 2 HIGH · 8 MEDIUM · 5 LOW**
**Verdicts:** 5 CONFIRMED · 9 ADJUSTED · 1 MERGED · 0 REJECTED · 1 half-finding rejected (PERF-011 capacity).
**Deviation from the auditor's draft:** 1 CRITICAL de-escalated to HIGH
(the report's own CRITICAL band requires regressions to be *silent*; they are not),
1 merge into SRCH-001, 8 de-escalations, 8 evidence corrections, 2 rejected
remediations (PERF-006 fix #3, PERF-011 recommendation #2), 1 new defect found
inside an existing finding (the `percentile()` API break).

**The auditor's methodology caveats are honest and unusually good.** The volume
disclosures are correct, the Redis/locmem distinction is correct, and refusing to
file a connection-pooling problem because "filing one would be speculative" is
exactly right. Seven items are nonetheless missing — see *Methodology gaps*.

---

## Cross-Phase Reconciliation

### The central question: is PERF-002 a duplicate of SRCH-001?

**Verdict: MERGED. `SRCH-001` (CRITICAL) is the record; PERF-002 is not a
separate finding.**

The phase-08 handbook explicitly deferred this work: *"13 must assume SRCH-001's
fix landed, or it will re-measure an 08-owned defect."* Phase 13 did re-measure
it, and the report is candid about the overlap — but the "**Cross-reference.**
This is *not a re-file*" paragraph overstates the case. Applying the merge test
literally:

| Test | PERF-002 vs SRCH-001 |
|---|---|
| Same code path | **Yes** — `listings_query.py:183-186`, reached from the same two anonymous endpoints |
| Same defect | **Yes** — one `features__slug=` JOIN per element of an unbounded list |
| Same failure mode | **Yes** — backend terminated, whole shared DB into crash recovery |
| Same fix family | **Yes** — bound the list in the DTO; change the join shape |
| New evidence | **Yes** — `COUNT(*)` row-count amplification table; the `Memoize`-per-feature plan shape; the OOM mechanism rather than "slow query" |
| New remediation | **Yes** — a single composite join + grouped `Count` replaces N nested loops with a constant-shape plan |

The new evidence is genuinely useful and should not be discarded; the new
remediation is materially better than "truncate the list", because a cap alone
leaves a 29-feature legitimate query on a 61-JOIN plan. Both belong on SRCH-001
as supporting evidence and an added remediation. Filing them separately creates
two owners for one defect and invites a partial fix (cap without join collapse)
that leaves a bounded-but-still-quadratic plan.

**Ownership correction carried into SRCH-001's remediation set:**

1. **Bound the input** — `max_length` on `ListingsQueryParams.feature_slugs` plus
   truncation in `build_queryset` (unchanged from SRCH-001; the availability half).
2. **Collapse the join** — a single `filter(features__slug__in=…)` with a
   `Count(..., filter=Q(...))` annotation compared to `len(set(feature_slugs))`,
   replacing the loop and the `distinct()` (the performance half; **new**).
   The AND-of-features semantics are preserved exactly.
3. **Keep DB-004 separate** — `statement_timeout`/`lock_timeout` are a
   prerequisite that bounds the symptom, not the fix. SRCH-001 already says this.

### Resolving the crash-recovery discrepancy (phase 08 "~30 s" vs phase 13 ">200 s")

**Verdict: not a conflict. The two numbers measure different quantities, and
neither is portable.**

Phase 08's 30.11 s is the **request wall-clock until the backend died** — its own
reproduction block reads *"a 30.11 s query after which PostgreSQL terminated the
backend mid-request"*. Phase 13's >200 s is the **crash-recovery window after the
kill**. The outage an attacker observes is the *sum* of the two.

I decomposed the sum on an isolated `postgres:18-alpine` (18.6) container with a
700 MB limit, a 3 M-row table, ~888 MB of un-checkpointed WAL, and a
memory-exhausting hash aggregate:

```
time_to_kill_s      = 12.00     <- analogue of phase 08's 30.11 s
recovery_window_s   =  8.00     <- analogue of phase 13's ">200 s"
total_s             = 20.00

server log:
  client backend (PID 151) was terminated by signal 9: Killed
  FATAL:  the database system is not yet accepting connections
  LOG:  redo done at 0/38FC5110 ... elapsed: 6.90 s
  LOG:  database system is ready to accept connections
```

**The recovery term is WAL-redo-bound, not query-bound.** 6.90 s of the 8.00 s
window was `redo done` replaying ~888 MB of dirty pages; the remainder was the
end-of-recovery checkpoint. So the recovery window scales with *everything written
since the last checkpoint* — other tenants, other processes, background jobs — and
is unbounded from the application's point of view. That is exactly why phase 13
(whose isolated instance was simultaneously hosting other agents' probes) saw
>200 s while phase 08 (a quieter instance) saw a shorter window after a comparable
kill.

**What this means for the record.** Neither figure should be quoted as "the
outage lasts N seconds". The defensible statement is: *the outage equals
time-to-kill plus WAL-redo time; the second term is unbounded from the
application, and the deployment ships with no `statement_timeout`, no
`lock_timeout`, and a 1 GB DB container default (`DB_MEM_LIMIT` unset in every
`.env.*`, so `docker-compose.yml:15` applies).* That makes SRCH-001's CRITICAL
**stronger**, not weaker, and makes **DB-004 (no `statement_timeout` /
`lock_timeout`) a co-equal P0** rather than a mere prerequisite.

**One evidence-provenance note.** The source report quotes the kill line as
`server process (PID 87) was terminated by signal 9: Killed`. PostgreSQL 18 emits
`client backend (PID …) was terminated by signal 9: Killed` — `server process` is
the pre-18 wording. The *mechanism* is exactly right (I reproduced it), so the
finding stands on this validation's own evidence; but the quoted line should not
be presented as a verbatim capture.

### Other cross-phase overlaps — checked, deliberately not duplicated

- **DB-004** (no `lock_timeout` / `statement_timeout`) — not re-filed. Confirmed
  still absent from `src/` and `docker/`. Now rated **co-equal P0 with SRCH-001**
  by this report's WAL-redo finding, which DB-008's phase-03 report did not cover.
- **DB-008** (whole-sweep transactions) — not re-filed. PERF-013 correctly
  restricts itself to *cost quantification*. Confirmed `recompute_normalized_prices`
  wraps its sweep in one `transaction.atomic()` (`recompute_normalized_prices.py:51-53`).
- **SRCH-006 / SRCH-007 / SRCH-014** — the report credits the search cache's
  invalidation as correct and re-files only effectiveness (PERF-006, PERF-007).
  That is the right division; no overlap.
- **ENT-001** (`PROMETHEUS_MULTIPROC_DIR` unset outside the prod override) —
  phase 01 adjudicated it MEDIUM because the prod override *does* set the
  variable. This report's PERF-011 correctly cross-references it. **My
  re-examination agrees with ENT-001**: raising `workers` is *not* blocked by the
  metrics variable. It is blocked by the CPU and memory quotas (see PERF-011).
- **OPS-001 / CFG-002 / ENT-004 / TEST-002** — CI is already red on at least three
  independent counts (bandit, lint/typecheck, and now the load-test job per
  PERF-001). No new conflict, but it materially changes the *context* of PERF-001:
  a red `load-test` job adds a fourth red check rather than creating the first
  silent one.

---

## Detailed Findings

### PERF-001 — [HIGH] — The CI p95 latency gate is broken in **both** directions: the shell half can never fail, the Python half always throws

| Field | Value |
|---|---|
| **ID** | PERF-001 |
| **Type** | CI-GUARD DEFECT / DEPENDENCY DRIFT (audit-input and code defect) |
| **Severity** | **HIGH** (auditor: CRITICAL) |
| **Files** | `.github/workflows/ci.yml:499-506`; `src/benchmark/locustfile.py:29-43`; `pyproject.toml:218`; `uv.lock:903-904` |
| **Status** | Open — P0 |

#### Defect A — the `awk` block is inert (auditor's claim, CONFIRMED by reproduction)

`locust` is `>=2.20.0` in `pyproject.toml:218` and locked at **2.46.6**
(`uv.lock:903-904`). Running the repo's own `locustfile.py` headless inside the
project image and dumping the real CSV:

```
Type,Name,Request Count,Failure Count,Median Response Time,Average Response Time,
Min Response Time,Max Response Time,Average Content Size,Requests/s,Failures/s,
50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%
GET,search,1,0,718.20,718.20,705.05,725.51,512.0,0.36,0.0,710,720,720,720,720,1700,1700,1700,1700,1700,1700
,Aggregated,13,0,710,866.70,702.60,1714.37,512.0,4.66,0.0,710,720,720,720,1700,1700,1700,1700,1700,1700
```

Column 1 is the HTTP `Type`; the aggregate row's name is the literal
`Aggregated` with an **empty** method. Column 6 is `Average Response Time`
(866.70); the real p95 is column 16 (1700). Replaying `ci.yml:500-506`
byte-for-byte against that file:

```
ACTUAL_P95=[]
p95 ms within SLO of 500ms
CI_WOULD_FAIL=no
```

Both of the auditor's sub-claims hold: `$1 == "Total"` matches zero rows, and `$6`
is the average, not p95.

#### Defect B — the effective gate is *also* broken, and the auditor missed it

The auditor states at its own line 91 that `locustfile.py:88-95`'s `_assert_p95`
hook "**is** correct and does set the process exit code, so it is the effective
gate", and treats the `awk` block as "dead code". That premise is wrong:

```python
# src/benchmark/locustfile.py:36-37
stats = environment.runner.stats
p95 = stats.get("Total", "NONE").percentile(0.95)
```

In locust 2.46.6, `StatsEntry.percentile` is:

```python
def percentile(self) -> str:      # no arguments; returns a formatted report row
    if not self.num_requests:
        raise ValueError("Can't calculate percentile on url with no successful requests")
    tpl = f"%-{STATS_TYPE_WIDTH}s %-{STATS_NAME_WIDTH}s %8d ..."
    return tpl % ((self.method or "", self.name) + tuple(...) + (self.num_requests,))
```

`.percentile(0.95)` therefore raises before the SLO comparison is ever reached.
Running the repo's real locustfile against a server whose every response takes
~700 ms (i.e. a 1 400 % breach of the 500 ms SLO):

```
[ERROR/locust.main] Uncaught exception in event handler:
Traceback (most recent call last):
  File ".../locust/event.py", line 47, in fire
    handler(**kwargs)
  File "/app/src/benchmark/locustfile.py", line 37, in _assert_p95
    p95 = stats.get("Total", "NONE").percentile(0.95)
TypeError: StatsEntry.percentile() takes 1 positional argument but 2 were given
[INFO/locust.main] Shutting down (exit code 2)

LOCUST_EXIT=2
```

The correct API is `StatsEntry.get_response_time_percentile(0.95)`.

**Consequence: the `load-test` job exits non-zero on every run, at any latency.**
`ci.yml:493-506` is a single `run:` block; GitHub Actions' default Linux shell is
`bash -e {0}`, so a non-zero exit from `uv run locust` fails the step before the
`awk` block is even reached. The step fails for a reason that has nothing to do
with latency — and the `P95_SLO` comparison never executes.

#### Severity: CRITICAL → HIGH, and why

The report's own CRITICAL band is *"A deployed guard is inert, so a known
production performance risk is unenforced and **regressions are silent**."*
That band does not fit. Regressions are **not** silent here: the `load-test` check
is red on every push. A permanently-red job is a different failure from a
permanently-green one — it destroys signal rather than manufacturing false
reassurance, and the correct remediation is different (repair the gate so it can
go green and then mean something, versus delete a misleading no-op).

**The gate cannot fail *because of latency* in any configuration reachable from
the lockfile.** `pyproject.toml:218` allows `>=2.20.0`, but CI installs from
`uv.lock` via `uv sync --frozen` (`ci.yml:412`), which pins 2.46.6 exactly. A
developer running `uv run locust` against an older locust would get the hook
working and the `awk` still inert; a developer on 2.46.6 gets the hook broken and
the `awk` still inert. There is no configuration in which the *combination* gates
latency correctly.

**Can it be configured to work?** Yes, and cheaply — which is why this is HIGH and
actionable rather than merely alarming. Three edits:
1. `p95 = stats.get("Total").get_response_time_percentile(0.95)`.
2. Delete the `awk` block, or replace it with a header-name parse
   (`csv.DictReader` → `row["Name"] == "Aggregated"` → `row["95%"]`) **plus** an
   assertion that the value is non-empty, so a future locust format change fails
   loudly instead of silently disabling the check.
3. Pin `locust` to the major/minor that the hook was written against, or better,
   add a unit test that builds a `StatsCSV` from a synthetic `StatsEntry` and
   asserts the hook extracts a p95. That test is the only thing that would have
   caught this when `uv.lock` moved.

**Impact restated honestly.** The auditor's "reproduced live: real p95 8 600 ms
reported `PASS` against a 500 ms SLO" is a *valid demonstration of defect A* but
it is **not** a demonstration of CI impact: it used a 60 000-ad synthetic dataset,
whereas the CI load test seeds **120** ads (`ci.yml:456`) and runs 60 s. No latency
this project can produce at 120 ads would breach a 500 ms p95. The gate is
non-functional as a matter of *construction*, not as a matter of *observed
breach* — and that is a stronger claim than the one the report makes.

#### Required fix

Per the project's "production code is king" rule, the **locustfile is production
code** and the `awk` block is the stale artefact. Fix the hook; delete the shell
duplicate rather than maintaining two parsers.

---

### PERF-002 — [MERGED → SRCH-001, CRITICAL] — `?features=` memory blowup

| Field | Value |
|---|---|
| **ID** | PERF-002 |
| **Type** | UNAUTHENTICATED AVAILABILITY DEFECT |
| **Severity** | **CRITICAL** (as `SRCH-001`) |
| **File(s)** | `src/backend/apps/ads/services/listings_query.py:57,183-186`; `src/backend/apps/search/views/search.py:101`; `src/backend/apps/ads/views/listings.py:249` |
| **Disposition** | **Not a separate finding.** See *Cross-Phase Reconciliation*. |

**Mechanism re-derived independently.** `ListingsQueryParams.feature_slugs` is
`list[str] = Field(default_factory=list)` with no `max_length` and no validator
(`listings_query.py:57`); the builder emits one JOIN per element followed by
`distinct()` (`listings_query.py:183-186`); the list arrives from
`request.GET.getlist("features")` on two unauthenticated endpoints. The
row-count multiplication the report describes (N nested loops over
`ad_features`, each feeding the next) is the standard consequence of that shape,
and phase 08 already measured the superlinear wall-clock independently
(10→1.31 s, 20→…, 40→7.88 s, 60→19.90 s, then `signal 9`).

**What phase 13 adds, and it is worth keeping:**

1. **The OOM mechanism rather than "slow".** I reproduced the SIGKILL on an
   isolated PG 18 and captured the exact modern log line
   (`client backend … was terminated by signal 9: Killed`) together with the
   `redo done … elapsed: 6.90 s` recovery. This converts SRCH-001 from "a slow
   query" into "an unbounded-memory query that removes the shared database from
   service", which is the correct CRITICAL justification.
2. **The composite-join remediation**, which is strictly better than truncation
   alone: a single `features__slug__in=[…]` with a filtered `Count` annotation
   compared against `len(set(feature_slugs))` yields a **constant-shape plan**
   regardless of how many values are sent, and preserves AND-of-features
   semantics exactly. Truncation alone leaves a legitimate 29-feature query on a
   61-JOIN plan.

**What does not survive.** The absolute millisecond table rests on a synthetic
60 000-ad dataset and a 60 000-row `COUNT(*)` that the report itself says OOM-killed
the backend. Those numbers are not reproducible on the shipped 1 GB DB container.
Keep them as *shape* evidence; do not quote them as timings.

---

### PERF-003 — [HIGH] — `rollup_daily_metrics`: an N+1 write loop inside one 305 s transaction

| Field | Value |
|---|---|
| **ID** | PERF-003 |
| **Type** | RUNTIME-DEFECT (background job) |
| **Severity** | **HIGH** (held) |
| **File(s)** | `src/backend/apps/analytics/management/commands/rollup_daily_metrics.py:43-73,101-113`; `src/backend/apps/core/utils/advisory_lock.py`; `src/backend/apps/core/utils/scheduler.py:70-73` |
| **Status** | Open — P1 |

**Verified.** The command is in `DAILY_COMMANDS` (`scheduler.py:70-73`), so it runs
every day on the default deploy path. It wraps the whole job in one
`transaction.atomic()` (`:43`) that also holds
`pg_advisory_xact_lock(AdvisoryLockId.ROLLUP_DAILY_METRICS)` (`:44`), and iterates
the aggregate issuing `update_or_create` per row (`:101-113`) — a `SELECT` plus an
`INSERT` or `UPDATE` each. The aggregate itself is one grouped query. Cost is
linear in *active* ads.

**The drop-in fix is valid.** `DailyAdMetrics.Meta.constraints` carries
`UniqueConstraint(fields=["ad","date"], name="uq_daily_ad_metrics_ad_date")`, so
`bulk_create(..., update_conflicts=True, update_fields=[...],
unique_fields=["ad","date"])` is correct against the shipped schema — I verified
the constraint rather than assuming it.

**Corrected: the causal attribution.** The report attributes ~99.97 % of the
305 s to *"roughly 120 000 sequential round trips … about 2.5 ms of pure
per-statement overhead per row."* That does not survive scrutiny:

- 2.54 ms per statement on a co-located connection is an order of magnitude above
  a local round trip; the per-row cost is dominated by the **write path** — the
  FK check against `ads`, the unique-index probe on `(ad, date)`, the index
  insert, and the WAL record — not by statement dispatch.
- The consequence matters for planning: the report's "305 s → a few seconds"
  projection assumes the loop was latency-bound. If it is write-bound, the win
  comes from doing the same 60 000 writes **in one pass** (fewer index
  maintenance events, far less per-statement overhead, no per-row round trip),
  which is still a large win — but it should be *measured*, not asserted.

**Required fix (unchanged in substance, restated with correct expectations):**
one `bulk_create(update_conflicts=True)`. Replace the projection "a few seconds"
with "measure before/after"; if the job still exceeds a few seconds, the residual
is real write volume and belongs in a capacity discussion, not a code fix.

**Not re-filed:** the `timestamp__date=yesterday` non-sargable predicate. The
report measured it at 108.5 ms parallel vs 117.3 ms sequential for the sargable
form and correctly declined to file it. That is a good call and is preserved.

**Not a duplicate of DB-008.** DB-008 owns the *transaction-boundary* shape of
`archive_sweep` and `recompute_normalized_prices`. This is a different command
with a different defect — an N+1 write loop, not an all-or-nothing sweep.

---

### PERF-004 — [MEDIUM] — `render_trust_badge`'s prefetch detection can never fire, costing one failing `SELECT` per card

| Field | Value |
|---|---|
| **ID** | PERF-004 |
| **Type** | RUNTIME-DEFECT (N+1) + DOC-UPDATE (the inline comment) |
| **Severity** | **MEDIUM** (auditor: HIGH) |
| **File(s)** | `src/backend/apps/trust/templatetags/trust_tags.py:61-80`; `src/backend/templates/ads/partials/ad_list.html:122`; `src/backend/apps/ads/services/listings_query.py:138`; `src/backend/apps/moderation/services/auto_moderation.py:280-288` |
| **Status** | Open — P2 |

**Mechanism confirmed, and the reasoning is sound.** `SellerTrustScore.user` is a
reverse `OneToOneField`. `prefetch_related("user__trust_score")` is present on
the production path (`listings_query.py:138`) and *does* collapse to one batched
query — but for a descriptor relation Django's `prefetch_one_level` calls
`setattr(obj, cache_name, val)`, which routes through
`ReverseOneToOneDescriptor.__set__` into the **field cache**, not
`_prefetched_objects_cache`. So:

```python
prefetched_cache = getattr(user, "_prefetched_objects_cache", None)
if isinstance(prefetched_cache, dict) and "trust_score" in prefetched_cache:
```

is **always False**, and the tag always takes the `else` branch. Inside it,
`getattr(user, "trust_score", None)` returns `None` for an absent row **without a
query** — because `RelatedObjectDoesNotExist` subclasses both
`model.DoesNotExist` **and `AttributeError`**, which is exactly why `getattr`'s
default works. The code then falls into `SellerTrustScore.objects.get(user=user)`,
a query that is **guaranteed to fail** on that row. The inline comment at `:61-66`
— "when the relation has been prefetched … accessing `user.trust_score` does NOT
hit the database — so the fallback is skipped entirely" — is **factually wrong**
for the reverse-one-to-one case.

**Why MEDIUM, not HIGH.** The extra query only appears when the row is
**absent**. When the row exists, `getattr` resolves from the field cache and
issues nothing. The absence rate is bounded: `TrustCalculator().calculate_and_save`
runs on every auto-moderated publish (`auto_moderation.py:280-288`) — inside a
bare `except Exception` that logs and continues, so a failed write is permanent
for that seller — and admin-created ads, `moderation.admin_actions.approve_ad`,
and the seed path bypass it entirely. The measured cost is 24 index-backed
`SELECT … LIMIT 1` round-trips per page, roughly 5–10 ms against a ~420 ms page:
about 2 %. The defect is real, the fix is correct and trivial, and the comment
must go with it — but this is not HIGH.

**Corrected: the "why the existing guards are green" section.** The finding
quotes a comment in `test_search_query_count.py` containing
`Bound raised from 35 to 100 in response to 13-PERF-004 recommendation #3`. **That
text does not exist in the repository** (see VAL-002 and PERF-014). The *other*
half of the claim survives and is verified: `test_ad_detail_queries.py:47,65` and
`test_search_query_count.py` both seed a `SellerTrustScore` row before asserting,
which is precisely what hides the absent-row branch.

**Required fix.** Drop the `.get()` fallback and the detection dance; read the
value and treat "no row" as the answer:

```python
trust_score = getattr(user, "trust_score", None)   # field cache OR one query, never 2
if trust_score is None:
    return ""
```

Delete the incorrect comment with it. No test-bound change is required by this
finding (see PERF-014 for why).

---

### PERF-005 — [MEDIUM] — `send_alerts` runs one FTS query per saved search inside one lock-held transaction

| Field | Value |
|---|---|
| **ID** | PERF-005 |
| **Type** | RUNTIME-DEFECT (background job) |
| **Severity** | **MEDIUM** (auditor: HIGH) |
| **File(s)** | `src/backend/apps/search/management/commands/send_alerts.py:64-70,100-136,138-153`; `src/backend/apps/search/services/alert_query.py:27-99,134-163`; `src/backend/apps/core/utils/scheduler.py:70-77` |
| **Status** | Open — P2 |

**Verified.** `handle()` wraps `_collect_alerts()` in one `transaction.atomic()`
that holds `pg_advisory_xact_lock(ALERT_DELIVERY_TASK)` (`send_alerts.py:64-70`),
and `_collect_alerts()` iterates every active `SavedSearch`, calling
`find_matching_ads()` per search (`:112-115`). Each call builds a **fresh** FTS
queryset (a new `SearchQuery`, `SearchRank` annotation and vector filter) against
the saved search's own language (`.`alert_query.py:48-69`). The structure is
exactly as described.

**Why MEDIUM, not HIGH.** The cost is `O(active_saved_searches × FTS_cost)` and
nothing more. The report's own measurement is 40 searches → 7.6 s, and it
extrapolates 1 000 → ~190 s. The scheduler's `SCHEDULER_COMMAND_TIMEOUT` is
1 800 s and the scheduler container is allocated `SCHEDULER_CPUS=0.5`. A linear job
that reaches ~10 % of its own timeout at a thousand saved searches is not
"monopolising the shared database" — the report's HIGH band requires a
demonstrated cost that "monopolises the shared database", and the extrapolation
does not reach that. It *is* a real, structural, cheap-to-fix cost with an
unbounded input, which is the MEDIUM band.

**Corrected: the "secondary cost" is misattributed.** The finding says
*"`record_notifications` calls `bulk_create(…, ignore_conflicts=True)` **per saved
search** … immediately followed by `saved_search.save(update_fields=[…])` — 2 M
extra statements for M matches"* and cites `immediate_alerts.py:98-101`. That
pattern is real, but it is **not on this path**. `send_alerts` does the opposite
of what is described: it accumulates `notifications_to_create` and
`analytics_events` across the entire loop and issues **one** `bulk_create` each in
`_persist_alerts()` (`send_alerts.py:138-153`). The per-search
`record_notifications` + `save()` pair lives in
`apps/search/services/immediate_alerts.py:98-101`, a *different* command path.
The batching the report recommends for the daily job is **already implemented
there**; only the immediate-alert path still does it per row, and that path is
default-off.

**The dormant related finding is correctly characterised.** `find_matching_saved_searches`
(`alert_query.py:134-163`) iterates every active saved search on the ad-publish
path, issuing a `Category.objects.get()` + `get_descendants()` per search with a
category and an `Ad.objects.filter(pk=…, vector=…).exists()` per search with a
query — and it is invoked from a `post_save` signal **inside the bot's request
handler** (`apps/moderation/signals.py:66,73-75`). Gated by
`IMMEDIATE_ALERTS_ENABLED`, default `False`. Correctly filed as dormant rather
than inflated. The recommendation — invert the daily loop by grouping distinct
`(language, query)` pairs and intersecting in Python, with a `--limit` / batched
loop as the honest interim — is right, avoids a task queue, and matches the
project's avoid-overengineering rule.

---

### PERF-006 — [MEDIUM] — For ≥1 000 matches the search cache recomputes the count on every hit

| Field | Value |
|---|---|
| **ID** | PERF-006 |
| **Type** | CACHE-EFFECTIVENESS DEFECT |
| **Severity** | **MEDIUM** (auditor: HIGH) |
| **File(s)** | `src/backend/apps/search/views/search.py:126-130,138-144,307-317`; `src/backend/apps/search/services/cache.py:41,133`; `src/backend/templates/ads/partials/ad_list.html:92-96` |
| **Status** | Open — P1 (fixes #1 and #2 only; see below) |

**Defect confirmed exactly as described.** The producer slices in Python —
`list(filtered_qs.values_list("id", flat=True))[:SEARCH_CACHE_MAX_HITS]`
(`search.py:126-130`) — so `len(cached_ids)` is *exactly* `SEARCH_CACHE_MAX_HITS`
(1 000, `cache.py:41`) and never more. `_resolve_search_count` branches on
`len(cached_ids) < SEARCH_CACHE_MAX_HITS` (`search.py:307`), so **any query with
≥1 000 matches falls through to `:311-317` and re-runs the full FTS `COUNT(*)` on
every cache hit**. The cache is bypassed for the count precisely in the broad-query
case it exists to serve. Verified structurally; the `SWRCache` is otherwise sound
— `SEARCH_CACHE_MAX_ENTRY_BYTES = 512 KB` comfortably admits a 1 000-int list, so
the entries really are cached.

**Why MEDIUM, not HIGH.** The report's HIGH rests on *"WARM … same URL: 510 ms
wall, 54 SQL"* against `PerformanceSLO.P95_SLO_MS = 500`. That is **one** sample,
on a synthetic 60 000-ad dataset, with `DEBUG=1`, no TLS, no gzip, database
co-located, and a term deliberately chosen to match 14 194 rows. It is not a
percentile, and the report criticises exactly this fallacy in PERF-012c when it
finds it in `test_search_slo.py` (VAL-003). The finding's own volume-dependence
paragraph concedes the cost scales with *match count*, which places it in the
MEDIUM band ("real but conditional on data volume") by the report's own
definition. The **defect is worth fixing**; the **SLO-breach framing is not
supported**.

#### Fix #1 — push the `LIMIT` into SQL. **ACCEPT.**

`filtered_qs.values_list("id", flat=True)[:SEARCH_CACHE_MAX_HITS]`. One line.
The plan changes from a full sort (`external merge Disk: 7952 kB`, ~22 MB of temp
I/O per cold query) to a `top-N heapsort` bounded at 1 000 rows. Semantics are
unchanged: `len(cached_ids)` is still `min(matches, 1000)`, so the `search.py:307`
branch behaves identically.

#### Fix #2 — stop recomputing the count at the cap. **ACCEPT, with a behaviour change on the record.**

Return `SEARCH_CACHE_MAX_HITS + 1` and set `results_truncated = True` rather than
rebuilding the FTS queryset. This is a **deliberate user-visible change**: the
displayed count becomes "1 001+" instead of the true total. The template already
has the notice (`ad_list.html:92-96`:
*"Over 1,000 results found. Showing the first 1,000."*), and `has_results` only
tests `total_count > 0`, so nothing breaks — but this must ship as a *product
decision*, with the notice verified in a rendered page, not as a silent
refactor.

#### Fix #3 — raise `work_mem`. **REJECTED AS WRITTEN. This is the finding's real risk.**

The premise is factually right and I confirmed the deployed baseline on an
isolated PG 18.6: **`work_mem = 4MB`, `max_connections = 100`.** Nothing in
`src/`, `docker/`, or any `docker-compose*.yml` sets `work_mem`, `shared_buffers`,
or `max_connections`. And `DB_MEM_LIMIT` is unset in **every** `.env.*` file, so
`docker-compose.yml:15` applies: **a 1 GB database container**, with
`DB_CPUS = 2.0` (`:16`).

`work_mem` is a **per-sort/per-hash-node, per-worker, per-connection** allocation,
not a per-query cap. The report's proposal of "32–64 MB for a 3-worker sync
deployment" is only safe if exactly one node allocates it. On this deployment:

- The plan the fix is *for* is the `?features=` nested-loop stack with **one
  `Memoize`/hash node per feature** (see PERF-002). At 60 features × 64 MB that
  is ~3.8 GB for a **single backend** — more than triple the entire container.
  Raising `work_mem` server-wide converts a 200 s crash into an immediate OOM of
  the *first* concurrent attacker, and widens the blast radius from one request to
  every other connection's memory headroom.
- With `max_connections = 100` and even a modest 2 nodes per query, 64 MB gives a
  worst case of 12.8 GB against a 1 GB cap.

**The correct disposition is: do not change `work_mem` at all.** Fix #1 converts
the spilling full sort into a bounded top-N heapsort, and the `COUNT(*)` has no
sort — so after #1 lands, there is no node in this path that needs more than the
4 MB default. Fix #3 is unnecessary *because* of fix #1, and harmful *instead of*
it. If a future plan genuinely needs a larger `work_mem`, the only acceptable
form is a **per-role / per-session** `options` setting scoped to the web
connection (3 connections, not 100), and it must be sized against
`WEB_MEM_LIMIT`/`DB_MEM_LIMIT` and reviewed against the `?features=` plan shape.

The report's other two exclusions — no index on `ts_rank` (query-dependent
expression, would not generalise across `websearch` configs) and no larger
`SEARCH_CACHE_MAX_HITS` (makes PERF-010 worse) — are both correct.

---

### PERF-007 — [LOW] — The single-flight lock is a duplicate-write guard, not a stampede guard — **on the cold-miss path only**

| Field | Value |
|---|---|
| **ID** | PERF-007 |
| **Type** | CACHE-EFFECTIVENESS (documented trade-off, mischaracterised) |
| **Severity** | **LOW** (auditor: MEDIUM) |
| **File(s)** | `src/backend/apps/core/utils/swr_cache.py:20-24,86-88,107-112,121-150`; `src/backend/apps/search/views/search.py:132,148-151` |
| **Status** | Open — advisory |

**What is true.** On a **cold miss**, `_cold_miss_with_lock` (`:138-150`) returns
`default` to the loser; `get_cached_search_ids` maps that to `None`
(`cache.py`), and the search view then runs the full FTS query itself
(`search.py:148-151`). So on a brand-new search term, N concurrent requests do
execute N FTS queries. Confirmed.

**What is false.** The claim *"The lock serialises the writer; the losers all
execute `compute()` anyway — it prevents 49 duplicate cache **writes**, not 49
duplicate FTS queries. It is not a stampede guard; it is a duplicate-write
guard."* is **wrong for the stale-window path**, which is the common case:

```python
# swr_cache.py:107-112
if age < ttl + stale_ttl:
    # Stale but within the stale-serve window.
    # Single winner recomputes; everyone serves the stale value.
    if cache.add(lock_key, "1", lock_ttl):
        _recompute_and_store(key, producer, ttl, stale_ttl, max_size_bytes)
    return entry.value
```

There, the losers **do not** recompute — they return the stale value, and exactly
one winner recomputes. That is a textbook stampede guard. The helper has two
distinct states with two distinct (and both intentional) behaviours.

**And the framing "that instruction is the defect" is wrong.** The
`default`-and-fall-back contract is documented three times, coherently: the
module docstring (`:20-24` — *"Concurrent losers (lock held by another worker, no
stale value) receive `default`"*), the function docstring (`:86-88` — *"Callers
should fall back to a direct computation in this case"*), and the caller's
comment (`search.py:149-150` — *"Cold miss loser (lock held by another worker):
fall back to a direct FTS query so the response is never blocked"*). Blocking a
web request on another worker's recompute is the *worse* behaviour; choosing
"compute it yourself" is a deliberate latency-over-DB-load trade, not an oversight.

**Exposure today.** With `workers = 3` and the `sync` worker class, at most **3**
concurrent FTS evaluations for a brand-new term, each ~100 ms. The report concedes
this. The "scales directly with the worker count if the pool is ever widened"
argument is hypothetical — and see PERF-011 for why widening the pool is not on
the table.

**Verdict: LOW, advisory.** Option 1 from the report (short retry, then serve
stale, ~5 lines, existing primitives only) is a reasonable improvement and a
sensible opportunistic change — but the *correct* framing is "improve the
cold-miss path", not "the lock is not a stampede guard". It must not be treated as
a P1, and no task queue may be introduced.

---

### PERF-008 — [MEDIUM, ROI-gated] — The header materialises the whole `cities` table into every page

| Field | Value |
|---|---|
| **ID** | PERF-008 |
| **Type** | OVER-FETCHING (design property) |
| **Severity** | **MEDIUM** (held, evidence weakened) |
| **File(s)** | `src/backend/apps/core/context_processors.py:49-50,98`; `src/backend/templates/components/header_catalog.html:65-73`; `src/backend/apps/search/views/search.py:217-218` |
| **Status** | Open — P3, **blocked on a data-source decision** |

**Design property confirmed at all three sites.** `context_processors.py:98`
returns `list(City.objects.order_by("name"))` on **every** page, for every
request, authenticated or not; `header_catalog.html:65-73` renders one
`<li><button data-city-option=…>` per city; `search.py:217-218` adds a **second,
uncached** copy under `save_search_cities` on top of the context processor's. The
docstring at `:49-50` — *"A single indexed MPTT query is acceptable for the MVP (no
per-request profiling concern)"* — is the assumption this finding overturns, and
naming it is the right move.

**The volume reality.** The shipped fixture `apps/seed/fixtures/cities.json`
contains exactly **15** records. At 15 rows the whole cost is ~8 KB of HTML and
~0.2 ms. The report's 2.9 MB page weight and 61 ms query come from **5 015
synthetic rows the auditor injected specifically to expose the scaling**. The
report is explicit about this, which is commendable and does not rescue the
severity: by its own admission the finding is not observable in the shipped
system.

**Disposition, split by ROI:**

- **Do now (positive ROI, zero new dependencies):** remove the duplicate
  `save_search_cities` at `search.py:217` and reuse the context-processor list.
  This is pure waste — the same table is already materialised once per request.
- **Do not do yet (negative ROI today):** cache the header city list. Adding a
  cache entry plus an invalidation counter to serve 8 KB is exactly the
  overengineering the project rules forbid. It becomes worthwhile the moment a
  real country dataset is loaded — which is a **product decision, not a
  performance fix**, and is the actual prerequisite.

**One correction to the suggested mechanism.** The report proposes reusing "the
existing `invalidate_by_prefix` + `SEARCH_CONTENT_VERSION_KEY` 'bump a version
integer' mechanism". Two caveats: (a) `SEARCH_CONTENT_VERSION_KEY` is the *search*
content counter embedded in *search* cache keys (`cache.py`); the header's
category tree uses a **different** counter, `get_tree_version()`; (b)
`invalidate_by_prefix` falls back to a **no-op** on LocMemCache
(`swr_cache.py:210-222`) and requires Redis `delete_pattern` in production. Any
city-list cache needs its own version counter bumped by `load_cities`, and the
report does not name one.

**The asymmetry argument is retained** and is the strongest part of the finding:
the *category* submenu is already cached behind SWR because someone recognised
this pattern for the other tree, and the city list is the same shape with no
cache and no bound. That is a real inconsistency — it just does not have a
measurable cost at the shipped scale.

---

### PERF-009 — [MEDIUM] — `cat.get_children.exists()` in the header: a real N+1 with a **wrong** recommended fix

| Field | Value |
|---|---|
| **ID** | PERF-009 |
| **Type** | RUNTIME-DEFECT (N+1) |
| **Severity** | **MEDIUM** (held; remediation corrected) |
| **File(s)** | `src/backend/templates/components/header_catalog.html:108,199`; `src/backend/apps/core/context_processors.py:94-96` |
| **Status** | Open — P2 |

**N+1 confirmed.** `get_children` appears at exactly **two** call sites, both in
`header_catalog.html` (`:108` desktop nav, `:199` mobile nav) — a
related-manager query per **non-leaf root** category per site. The shipped
`apps/categories/catalog/categories.yaml` has **7 top-level** categories
(`real-estate, transport, goods, animals, services-jobs, business, charity`) and
**234** slugs total, so the maximum is 14 `SELECT 1 … WHERE parent_id = %s LIMIT 1`
statements per page — consistent with the reported 12–13 (some roots are leaves,
and `mptt`'s leaf short-circuit returns `none()` without a query). Each is
index-backed on the `parent_id` FK. The header does not use `prefetch_related`.
Correct in kind, though the report's "one per child category rendered in the
header" is a mischaracterisation — it is one per **root**, not per child.

**The recommended one-line fix does not work, and this is the substantive
correction.** The report proposes: *"Add `prefetch_related("children")` to the
`root_categories` queryset … Django evaluates a prefetched `get_children` from
cache without a query. **One line**, removes 12 queries."*

`Category` is a `django-mptt` `MPTTModel` (`apps/categories/models.py:8,14`), and
`mptt.models.MPTTModel.get_children` is **not** the `children` reverse relation.
Verified from the installed package:

```python
@raise_if_unsaved
def get_children(self):
    if hasattr(self, "_cached_children"):
        qs = self._tree_manager.filter(pk__in=[n.pk for n in self._cached_children])
        qs._result_cache = self._cached_children
        return qs
    else:
        if self.is_leaf_node():
            return self._tree_manager.none()
        return self._tree_manager._mptt_filter(parent=self)
```

It builds a **fresh** queryset from `_mptt_filter(parent=self)` and consults only
`self._cached_children` — the attribute populated by mptt's `cache_tree_children`
helper. `prefetch_related("children")` populates
`user._prefetched_objects_cache["children"]`, which this method **never reads**,
and Django's reverse related manager only reuses its prefetch cache when *no*
filtering is applied. So the proposed one-liner would add a prefetch and remove
**zero** queries. A repairer following the report would ship a no-op.

**Correct minimal fix (one query total, no prefetch semantics required):**

```python
# context_processors.py:94-96
"root_categories": list(
    Category.objects.root_nodes().filter(is_active=True).order_by("name")
    .annotate(has_children=Exists(Category.objects.filter(parent_id=OuterRef("pk"))))
)
```

```django
{# header_catalog.html:108 and :199 #}
{% if cat.has_children %}
```

One `SELECT` for all roots instead of up to 14, still a local and obvious change.
(The report's second option — serve the expandable branches from the cached
submenu markup — remains a reasonable longer-term shape, and the shared
`aria-controls="menu-{{ cat.id }}"` ids confirm the two views were designed to
compose.)

**Corrected: the "already-cached tree" premise is weaker than stated.** The
report quotes `apps/categories/views.py:60-68` as

```python
html = get_with_stale_revalidate(
    build_submenu_html, CATEGORY_SUBMENU_CACHE_TTL,
    cache_prefix="categories:submenu:", version_key=SEARCH_CONTENT_VERSION_KEY,
)
```

**Neither kwarg exists.** `get_with_stale_revalidate`'s signature is
`(key, producer, *, ttl, stale_ttl, lock_ttl, default, max_size_bytes)`
(`swr_cache.py:67-76`); the quoted call could not compile against the shipped
helper. The real code (`categories/views.py:51,63-70`) caches a **per-category,
on-demand HTMX fragment** under `category:submenu:<tree_version>:<slug>:<locale>`.
That is not "the identical category tree the header rebuilds" — it is a
lazily-fetched sub-branch for one category, and it does not include the header's
root-level expand affordance. The redundancy argument is real but weaker than
presented, and the supporting quote must be replaced.

**Also corrected:** the report cites
`components/categories/partials/mega_submenu.html:15` as carrying the same
pattern. That file does not exist at that path; the real one is
`templates/categories/partials/mega_submenu.html`, and a repo-wide grep of
`src/backend/templates` finds `get_children` in `header_catalog.html` **only**.

---

### PERF-010 — [MEDIUM] — The cache-hit restore sends a 35 KB statement with 1 000 `CASE…WHEN` arms per page view

| Field | Value |
|---|---|
| **ID** | PERF-010 |
| **Type** | OVER-FETCHING / STATEMENT-SIZE |
| **Severity** | **MEDIUM** (held) |
| **File(s)** | `src/backend/apps/search/views/search.py:134-144`; `src/backend/apps/search/services/cache.py:41` |
| **Status** | Open — P2 |

**Confirmed.** On a cache hit the view restores rank order with a positional
`Case`:

```python
ads = ads.filter(pk__in=cached_ids).order_by(
    Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(cached_ids)],
         default=len(cached_ids), output_field=IntegerField())
)
```

The id list is bounded by `SEARCH_CACHE_MAX_HITS = 1 000`, **not** by page size,
so the statement length, the `WHEN`-arm count and the bind count are all
independent of how many ads the user actually sees. A 24-row page produces a
statement with 1 000 conditional branches in its `ORDER BY`, and the ids appear
twice — once in `IN (…)`, once as 1 000 `WHEN` arms. `prepare_threshold: None`
(`settings/base.py:250,263`) correctly disables server-side prepares for
pgbouncer, so this is a parse/plan cost rather than a protocol failure, paid on
**every** page view of a cached search.

**What the report does not establish, and should not be read as established.** It
provides statement *sizes* and *bind counts* (hardware-independent, correct) but
**no latency measurement** for this statement. The impact is argued from parse
and plan cost, which is a legitimate engineering argument but is not a
measurement. This is fine — the deliverable is the shape, and the shape is
clearly wrong — but the report should not imply a measured per-request cost.

**Accepted fix (page slice).** The order is already known: it is the order of
`cached_ids`. So only the ids actually on the page need positional arms:

```python
page_ids = cached_ids[bottom:top]                       # already ordered by rank
ads = ads.filter(pk__in=page_ids).order_by(
    Case(*[When(pk=pk, then=i) for i, pk in enumerate(page_ids)],
         default=len(page_ids), output_field=IntegerField())
)
```

This cuts the statement from ~35 KB to ~800 bytes without touching the cache
format. The report is right to prefer this over `in_bulk(order)` + a Python sort
("3× more work for the same benefit") — that is correct proportionality under
the project's avoid-overengineering rule.

**Interaction to sequence (VAL-004).** This fix and PERF-006 fix #1 both change
the producer/consumer contract of `cached_ids`. If PERF-006 #1 introduces a SQL
`LIMIT`, the cached list is unchanged in meaning, so the two are compatible — but
they touch the same function and should land in one change with one test, not
as two independent patches that each assume the other's shape.

---

### PERF-011 — [MEDIUM, re-scoped] — Capacity: **REJECTED.** Observability: confirmed.

| Field | Value |
|---|---|
| **ID** | PERF-011 |
| **Type** | BEST-PRACTICE (observability) + REJECTED recommendation (capacity) |
| **Severity** | **MEDIUM** (observability half only) |
| **File(s)** | `gunicorn.conf.py:11-15`; `docker-compose.yml:219-259`; `.env.dev` / `.env.test` / `.env.prod`; `docs/ops/prometheus-slo-alerts.yaml:13-16,56-101` |
| **Status** | Open — P1 (alerts only) |

#### Half A — the SLO alert scope gap. **CONFIRMED, accept.**

Both latency alerts pin a single handler:

```promql
# prometheus-slo-alerts.yaml:61,64,100
django_http_response_duration_seconds_bucket{le="2.000", handler="search:search"}[14.4m]
django_http_response_duration_seconds_count{handler="search:search"}[14.4m]
rate(django_http_response_duration_seconds_bucket{handler="search:search"}[5m])
```

`/search/` is pinned; `ads:listings` — the highest-traffic page, the target of
`view_listings` in the load test's `BuyerJourneyUser`, and the page the load test
spends its heaviest weight on — has **no latency SLO and no alert**, even though
`PerformanceSLO.P95_SLO_MS` / `P99_SLO_MS` are written as generic constants in
`src/benchmark/constants.py`. A 10× regression on the main listing page is
invisible to the alert rules. A YAML change, no code, no risk. **Do this first.**

Caveat, already noted in the file's own header (`:13-16`): gunicorn runs 3
workers with `preload_app = True` and the default in-process registry, so each
`/metrics` scrape returns one worker's metrics and counter-based alerts are
untrustworthy. That is **ENT-001**. The new alert should land with, or after,
ENT-001's `child_exit` guard — otherwise it inherits the same defect.

#### Half B — "3 sync workers cap the tier at 3 in-flight requests; size `workers` to the core count". **REJECTED.**

The premise about gunicorn is right in substance and wrong in citation.
`gunicorn.conf.py:11-15` is:

```python
bind = "0.0.0.0:8000"
# Worker processes: 2 * CPU + 1 is the common heuristic; pinned at 3 for the
# container's expected allocation.
workers = 3
```

There is **no `worker_class` line**; `sync` is gunicorn's default, so the
conclusion (one in-flight request per worker) holds. But the *recommendation* is
contradicted by the deployment, and this is the decisive fact:

```yaml
# docker-compose.yml:252-253
mem_limit: ${WEB_MEM_LIMIT:-512m}
cpus: ${WEB_CPUS:-1.5}
```

**`WEB_CPUS` and `WEB_MEM_LIMIT` are set in no `.env.*` file** (verified across
`.env.dev`, `.env.test`, `.env.prod` and their `.example` counterparts). So the
shipped web container is **1.5 CPUs and 512 MB**.

The measured request is **74 % Python/template** (`ad_list.html` is the cost), i.e.
CPU-bound. The report's own recommendation is *"a worker count near the core count
is the right shape"* — but the core count is **1.5**. That means **1 or 2 workers,
not 3**. Today is already over-subscribed. Raising `workers` would:

- oversubscribe a 1.5-CPU quota with CPU-bound work, so per-request latency
  degrades and the p95 gets *worse*, not better;
- multiply per-worker RSS inside a 512 MB cap (three Django workers with
  `preload_app = True` already consume most of it), risking an OOM kill of the
  **web** container — the same failure class as SRCH-001, self-inflicted;
- and, per the report's own corollary, "if the worker count is ever raised … the
  pooling decision becomes live and must be revisited in the same change" — i.e.
  the recommendation's own precondition is unaddressed.

On the `PROMETHEUS_MULTIPROC_DIR` question the task raises: **raising `workers` is
*not* blocked by it.** Phase 01's ENT-001 adjudicated the variable as set in the
prod override, so the multiprocess metrics path is consistent in production. The
blockers are the CPU and memory quotas, which ENT-001 does not address.

**Verdict: reject the capacity recommendation entirely.** The `workers = 3`
constant is a deliberate, documented choice ("pinned at 3 for the container's
expected allocation") made against a 1.5-CPU container. The throughput ceiling is
a property of the **host allocation**, not of `gunicorn.conf.py`. Changing
`gunicorn.conf.py` cannot raise it; changing `WEB_CPUS`/`WEB_MEM_LIMIT` can, and
that is a capacity/infrastructure decision, not a performance-audit action. This
is exactly the premature optimisation the project's "prove the cost before
proposing one" rule forbids.

The report's explicit *non*-filing of a connection-pooling problem — *"There is
no connection-pool problem to solve at this worker count, and filing one would be
speculative"* — is correct and is preserved as the right answer to that question.

---

### PERF-012 — [MEDIUM] — The load test targets URLs that are not routes, and `profile_queries` cannot be exercised

| Field | Value |
|---|---|
| **ID** | PERF-012 |
| **Type** | CI-GUARD DEFECT / OPS |
| **Severity** | **MEDIUM** (held) |
| **File(s)** | `src/benchmark/locustfile.py:67-75`; `src/backend/apps/ads/urls.py:14-17`; `src/backend/config/urls.py:19`; `src/backend/apps/core/management/commands/profile_queries.py:39,111-147,149-201`; `src/backend/apps/search/tests/test_search_slo.py`; `docs/ops/profiling.md` |
| **Status** | Open — P1 |

#### 12a — 33 % of generated traffic 404s. **CONFIRMED.**

```python
# locustfile.py:67-75
@task(2) def browse_category(self):     self.client.get("/c/electronics",        name="category-browse")
@task(1) def browse_subcategory(self):  self.client.get("/c/electronics/phones", name="subcategory")
```

The only category route is `category/<slug:category_slug>/` (`ads/urls.py:16`),
included at `config/urls.py:19`. There is **no `/c/` prefix** in `config/urls.py`
or in any included URLconf. `electronics` and `phones` are real slugs in the
shipped catalog (`apps/categories/catalog/categories.yaml:378,382`), and both are
**child** nodes, so the correct URLs are `/category/electronics/` and
`/category/electronics/phones/`. Task weights 2 + 1 out of 9 = **33 %** of
generated traffic. The CI step asserts no failure rate, so the 404s are silent.
The consequence is stated correctly and matters: **the most index-sensitive query
shape in the product — a category-scoped browse — is not load-tested at all**,
while a third of the load is spent on sub-millisecond 404s that pull the
aggregate p95 *down*.

#### 12b — `profile_queries` cannot assert anything in any shipped environment. **CONFIRMED, mechanism corrected.**

`SEED_SCALE_MIN_ROWS = 10_000` (`profile_queries.py:39`). The CI load test seeds
**120** ads (`ci.yml:456`). No shipped environment creates ≥10 000 published rows.
Below the threshold the command prints a WARNING (`:112-118`) and skips the
Seq-Scan assertion (`:126`), then unconditionally prints
`"Profiling complete — no Seq Scan on 'ads' at {row_count} rows"` (`:141-147`)
and exits **0** — which is why the report's conclusion ("indistinguishable from a
clean run") is right.

**Correction:** the report says *"`_scale_dataset()` returns early unless that many
published ads exist"*. **There is no `_scale_dataset()` in the command** (verified
by grep; the file has `handle`, `_build_queries`, `_explain`, `_has_seq_scan`). The
real mechanism is the `row_count >= SEED_SCALE_MIN_ROWS` guard at `:111`/`:126`,
and the command does **not** exit early — it runs all six `EXPLAIN`s regardless.
Same conclusion, different mechanism.

`profile_queries` is referenced only from `Makefile:385` — which invokes
`scripts/profile_search.py`, a *different* tool — and from
`docs/ops/profiling.md:66-82`. It is **not** in any workflow file. Confirmed.

The `_build_queries()` coverage gaps are all real and all material:
`user__is_declined=False` (a join `ListingsQuery.build_queryset` adds on **every**
real request), the `annotate_favorites` correlated `Exists`, the `?features=`
multi-select join, the cache-hit `CASE` restore, and `_resolve_search_count`'s
re-run at the cap. Additionally, `city_id=1` and `category_id__in=[1, 2, 3]`
(`:182,186`) are **hard-coded surrogate ids** that do not necessarily exist in
any environment — a defect the report did not flag.

#### 12c — `test_search_slo.py` is not an SLO gate. **CONFIRMED.**

It seeds **60** ads, issues **one** request, and asserts
`elapsed_ms <= PerformanceSLO.SEARCH_SLO_MS` (2 000 ms) — a **p99** constant
applied to a **single sample**. Its own docstring calls it *"the latency
regression test that every PR is gated on"*. At 60 rows the planner uses a
sequential scan regardless of which indexes exist, so it is structurally
incapable of detecting an indexing or plan regression. Keep it as a smoke test;
stop describing it as the SLO gate.

**Accepted fixes.** Correct the two URLs and assert a 0 % failure rate in the CI
step; extend `_build_queries()` with the missing production shapes and replace the
hard-coded ids with resolved ones; make the threshold a `--min-rows` argument;
add a nightly `profile_queries` job (the `ci-nightly.yml` workflow exists). And
re-baseline afterwards: with the dead task removed, the p95 the load test
measures will be materially worse than today's number. That is the point — and it
is also why PERF-001 must be fixed **first**, or the re-baseline is unobservable.

---

### PERF-013 — [LOW] — `recompute_normalized_prices`: 125 statements, 3.0 s, 120 `FOR UPDATE` batches

| Field | Value |
|---|---|
| **ID** | PERF-013 |
| **Type** | COST QUANTIFICATION for `DB-008` (not a new defect) |
| **Severity** | **LOW** (held) |
| **File(s)** | `src/backend/apps/currencies/management/commands/recompute_normalized_prices.py:26,51-53,85-100,113-117,141-144`; `src/backend/apps/core/utils/scheduler.py:55-65` |
| **Status** | Informational — sequence last |

**Verified.** The command wraps the whole sweep in one `transaction.atomic()`
(`:51-53`), iterates with `.iterator(chunk_size=500)` (`:85-87`), and per batch
issues `select_for_update().filter(pk__in=…).only("pk", "price_amount",
"price_currency", "price_normalized_eur")` (`:113-117`) plus a `bulk_update`
(`:141-144`). The `.only()` projection is correct. At 60 000 ads that is
120 lock-and-read batches + a handful of setup statements = the reported 125, in
one transaction, holding `RECOMPUTE_NORMALIZED_PRICES` for the whole run.

**Correctly scoped, correctly ranked.** The command is absent from
`HOURLY_COMMANDS` (`scheduler.py:55-65`) *and* from `DAILY_COMMANDS`
(`:70-73`) — it runs only when a human invokes it. At 3.0 s against a 1 800 s
`SCHEDULER_COMMAND_TIMEOUT`, this is the cheapest of the sweeps. The
`API-008`-dependent caveat about updated-row volume is correctly framed as a
dependency, not a measurement. The report's conclusion — "the transaction-shape
fix is `DB-008`'s to make; the only thing worth recording here is that this is
the *cheapest* of the sweeps and should be sequenced last" — is the right one
and is preserved unchanged.

---

### PERF-014 — [LOW] — The N+1 guard's `images` rationale is false; the rest of the charge rests on a quote that does not exist

| Field | Value |
|---|---|
| **ID** | PERF-014 |
| **Type** | DOC-UPDATE (test comment) |
| **Severity** | **LOW** (held, content substantially corrected) |
| **File(s)** | `src/backend/apps/search/tests/test_search_query_count.py:40-65`; `src/backend/apps/ads/services/listings_query.py:138`; `src/backend/templates/ads/partials/ad_list.html:107` |
| **Status** | Open — P3 |

**The central charge is unsupported.** The finding quotes this comment:

```python
# => ~40 baseline queries + search machinery (~15) = ~55, plus headroom.
# Bound raised from 35 to 100 in response to 13-PERF-004 recommendation #3
# (Documented: images is not in prefetch_related; the template's
#  ad.images.first is a prefetched relation so it does not query).
_QUERY_BOUND = 100
```

**That text does not exist.** The actual comment at
`test_search_query_count.py:40-64` reads, in substance:

- the search view's pipeline "inherently issues ~28 base queries — already
  exceeding the project-wide 16-query guard";
- it names **both** N+1 sources explicitly, including *"``render_trust_badge``
  (trust_tags.py:66) calls ``SellerTrustScore.objects.get(user=user)`` when the
  prefetched ``user__trust_score`` resolves to None, bypassing the prefetch"* —
  i.e. **it already documents PERF-004 by name**;
- *"Since this task only creates the test file, the bound is set to 100 —
  comfortably above the measured 80, with margin for minor variations, yet tight
  enough to catch a *new* per-ad N+1 (e.g. another un-prefetched relation would
  add ~24 queries → 104 > 100)"*;
- *"Once the two N+1 sources above are resolved, the bound should be tightened
  toward the ~32-query base."*

That is a **transparent, self-aware TODO with a measured baseline and a
prescribed remedy** — not a rationalisation, and not "how N+1s become
permanent". The report's three-point charge collapses to:

1. ~~"The guard was raised, not the defect fixed"~~ — the comment says the
   opposite: the bound is explicitly provisional pending the fix.
2. **The `images` sentence is genuinely false.** `ListingsQuery.build_queryset`
   specifies `prefetch_related("features", "user__trust_score", "images")`
   (`listings_query.py:138`), and `ad_list.html:107`'s `ad.images.first` resolves
   from that prefetch. **This is the finding that survives.**
3. **The cost misattribution is real but the conclusion is inverted.** The comment
   blames "localized-name lookups" for the 12 `categories` and 24–25
   `seller_trust_scores` queries. Those are PERF-009 and PERF-004, and both are
   fixable — so the comment is *under*-diagnosing, not over-claiming. The report's
   estimate that the post-fix budget is "closer to 10, not 46" is plausible but
   unmeasured; it should be established by fixing PERF-004 and PERF-009 and
   re-running, not asserted in advance.

**Corrected disposition.** Fix PERF-004 and PERF-009 first, then set the bound to
a number **derived from the measured post-fix inventory**, and correct the
`images` sentence. No test needs to change to make this finding true; the doc
comment does.

**Note for the record:** the same non-existent quote is reused in PERF-004's
"why the existing guards are green" section. Both instances must be corrected
together (VAL-002).

---

### PERF-015 — [LOW] — `docs/ops/profiling.md` overstates what `profile_queries` measures

| Field | Value |
|---|---|
| **ID** | PERF-015 |
| **Type** | DOC-UPDATE |
| **Severity** | **LOW** (held, claim 1 refuted) |
| **File(s)** | `docs/ops/profiling.md:24-42,44-64,66-101`; `Makefile:385-389`; `src/backend/apps/core/management/commands/profile_queries.py` |
| **Status** | Open — P3 |

**Claim 1 is false.** The finding states: *"**The tool cannot run.** … `make
profile` therefore prints the 'not enough data' branch and exits 0."*

`make profile` does **not** invoke `profile_queries`:

```make
# Makefile:385-389
profile:
	docker compose $(COMPOSE_FILES) exec -T web uv run python scripts/profile_search.py --iterations ...
```

`Makefile.ps1:193` does the same. And `docs/ops/profiling.md` documents them as
**two separate tools** — `## Running cProfile — scripts/profile_search.py` at
`:44-59` and `## Running EXPLAIN ANALYZE — profile_queries` at `:66-82`. The doc
is *more* accurate than the finding claims on this point. Worse, `:97` states
correctly and explicitly: *"The Seq-Scan assertion is **skipped** (with a
WARNING) when the published-ad count is below `SEED_SCALE_MIN_ROWS` (10k)."*
The doc describes the skip; the finding attributes to it a behaviour it does not
claim. The `:37` prerequisite ("seed >10k published ads") and the `:100`
instruction to `make up` are also present, and the latter is **wrong in the other
direction** — the dev stack does not seed 10 k ads, which is exactly PERF-012b's
gap, so the doc's own remediation is not achievable as written.

**Claims 2 and 3 survive, and they are the real content:**

- The command does not cover the production query shapes — `user__is_declined`,
  the `annotate_favorites` `Exists`, the `?features=` join, the cache-hit
  `CASE` restore, `_resolve_search_count`'s cap re-run — so a reviewer following
  the cadence table at `:30` would get a clean report while a new sequential scan
  shipped on the real path. The **"single best signal for query regressions"**
  framing (`:26`, via rules.md:226) is therefore too strong.
- The `≥10 000`-row threshold is the wrong axis: FTS cost scales with **match
  count** for a given term, not with table size. A 10 k-row table with a common
  term reproduces the problem; a 10 k-row table with a rare term does not. The
  command has no notion of a match-count target.

**Disposition.** Documentation-only, and the code change is small: soften the
"best signal" wording to describe what is actually checked; add the missing shapes
to `_build_queries()` (sharing the work with PERF-012b, so it lands once);
introduce `--min-rows`; fix the `make up` claim at `:100`; and add a pointer to
the browse path's N+1 budget guard (corrected per PERF-014). **No test or
production change is required by this finding.**

---

## Findings Requiring Architectural or Structural Change

**None of the fifteen findings requires an architectural or structural change.**
That is the report's strongest result, and it contradicts the source report's own
"Architecture-affecting: PERF-002, PERF-003, PERF-006, PERF-011" line. On
inspection, every accepted remediation is a local, additive change inside one
function, one template, one annotation, or one YAML file:

| Finding | Accepted change | Blast radius |
|---|---|---|
| PERF-001 | one function (`_assert_p95`) + delete one shell block | the `load-test` job |
| PERF-002 | one queryset builder (`ListingsQuery.apply_filters`) | merged into SRCH-001 |
| PERF-003 | one loop → one `bulk_create` | one management command |
| PERF-004 | one template tag | one template tag |
| PERF-005 | one loop's grouping | one management command |
| PERF-006 | one `[:1000]` slice + one branch | one view + one template notice |
| PERF-007 | optional ~5-line retry | one helper |
| PERF-008 | delete one duplicated expression | one view |
| PERF-009 | one annotation + two template call sites | one context processor |
| PERF-010 | one slice in one view | one view |
| PERF-011 | one YAML rule | one rules file |
| PERF-012 | two URLs + `_build_queries()` + a nightly job | benchmark + CI |
| PERF-013 | none (`DB-008` owns it) | — |
| PERF-014 | one comment | one test file |
| PERF-015 | doc wording + `_build_queries()` | one doc + one command |

**The only genuinely structural items in scope are inherited from other phases,
not introduced here**, and they are the two that should be sequenced first because
they are what make everything else survivable:

1. **Input bounds modelled as part of the DTO contract** (`SRCH-001`, plus
   `SRCH-011` / `SRCH-006` from phase 08). One `?features=` list from one
   anonymous visitor removes the shared database from service. The composite-join
   remediation from PERF-002 belongs here.
2. **Database-level execution bounds** (`DB-004`). No `statement_timeout`, no
   `lock_timeout`, anywhere. This validation's WAL-redo measurement (VAL-001)
   raises DB-004 from "prerequisite" to **co-equal P0**: today a single request
   can hold the database out of service for an interval the application cannot
   bound, because the recovery term is a function of the whole instance's write
   volume rather than of the offending query.

If the team wants one structural change from this phase, it is these two, and
neither comes from phase 13.

---

## VAL Findings (new — raised by this validation)

### VAL-001 — The crash-recovery window is WAL-redo-bound, which makes DB-004 a co-equal P0 with SRCH-001

**Type:** CROSS-PHASE CORROBORATION (the phase-08/phase-13 30 s vs >200 s
discrepancy, resolved).
**Severity:** informational (it changes no severity; it changes a priority).

The two numbers measure different quantities. Phase 08's 30.11 s is the request
wall-clock until the backend was killed; phase 13's >200 s is the recovery window
afterwards. Decomposed on an isolated `postgres:18-alpine` (18.6, 700 MB limit,
3 M rows, ~888 MB un-checkpointed WAL):

```
time_to_kill_s    = 12.00
recovery_window_s =  8.00   of which  redo done ... elapsed: 6.90 s
total_s           = 20.00
client backend (PID 151) was terminated by signal 9: Killed
```

**The recovery term scales with everything written since the last checkpoint** —
all tenants, all processes — not with the offending query. It is therefore
unbounded from the application's point of view, and it is why the same defect
yields 20 s on a quiet instance and >200 s on a busy one. With no
`statement_timeout` (DB-004) and a 1 GB `DB_MEM_LIMIT` default that ships to
production (VAL-001 of phase 08), nothing in the application bounds the outage.

**Consequence for the record:** quote neither figure as "the outage lasts N
seconds". The defensible statement is *time-to-kill + WAL redo, the second term
unbounded by the application*.

### VAL-002 — Six quoted artefacts in the phase-13 report do not exist in the repository

**Type:** AUDIT-INPUT DEFECT (evidence integrity).
**Severity:** **HIGH for the report as a repair source**, zero for the codebase.

None of the following changes a verdict, because each finding's *defect* was
independently confirmed. But a repairer who follows a non-existent quote will edit
the wrong thing, or ship a no-op:

| # | Quoted in the report as | Actual state |
|---|---|---|
| 1 | `test_search_query_count.py:14-31` — a comment containing `=> ~40 baseline queries + search machinery (~15) = ~55, plus headroom.` and `Bound raised from 35 to 100 in response to 13-PERF-004 recommendation #3` | Neither string exists. The real comment (`:40-64`) names both N+1s, states the measured 80, and prescribes tightening to ~32. **Also misquoted in PERF-004.** |
| 2 | `profile_queries` has a `_scale_dataset()` that "returns early unless ≥10 000 published rows" | No such function. The guard is `row_count >= SEED_SCALE_MIN_ROWS` at `:111`/`:126`, and the command does **not** exit early. |
| 3 | `components/categories/partials/mega_submenu.html:15` contains the same `get_children.exists` pattern | No such file. The real one is `templates/categories/partials/mega_submenu.html`, and `get_children` appears in templates **only** at `header_catalog.html:108,199`. |
| 4 | `apps/categories/views.py:60-68` calls `get_with_stale_revalidate(..., cache_prefix="categories:submenu:", version_key=SEARCH_CONTENT_VERSION_KEY)` | **Neither kwarg exists** on `get_with_stale_revalidate` (`swr_cache.py:67-76`); the call could not compile. The real cache key is `category:submenu:<tree_version>:<slug>:<locale>` (`:51`) and the version counter is `get_tree_version()`, not `SEARCH_CONTENT_VERSION_KEY`. |
| 5 | `gunicorn.conf.py` contains `worker_class = "sync"` | No such line. `sync` is gunicorn's default, so the conclusion holds, but the quote is not a quote. |
| 6 | PostgreSQL 18 log line `server process (PID 87) was terminated by signal 9: Killed` | PG 18 emits `client backend (PID …) was terminated by signal 9: Killed` (verified). `server process` is pre-18 wording. |

**Required action:** correct all six in the source report before it is used to
schedule work. The *findings* stand; the *evidence citations* must not be trusted
as repair instructions.

### VAL-003 — The report criticises the single-sample-as-percentile fallacy in PERF-012c and commits it in PERF-006

**Type:** CROSS-FINDING INCONSISTENCY (within phase 13).
**Severity:** informational — it is the direct cause of one severity.

PERF-012c correctly identifies that `test_search_slo.py` *"is a p99 constant
(`SEARCH_SLO_MS = 2000`) applied to a single sample — it is not a percentile
measurement"*. PERF-006 then justifies **HIGH** with *"WARM … same URL: 510 ms
wall"* against `PerformanceSLO.P95_SLO_MS = 500` — one sample, `DEBUG=1`, a
synthetic 60 000-row dataset, and a term chosen to produce 14 194 matches.
Applying the report's own standard to its own evidence, PERF-006's SLO-breach
claim does not hold, which is why PERF-006 is validated at **MEDIUM** here.

**Generalisable rule for the remaining phases:** a single-request timing is a
smoke measurement. It may establish *"this is in the right order of magnitude"*;
it may not establish *"this breaches a percentile SLO"*.

### VAL-004 — Rollout-safety: four coupled changes and one ordering constraint

**Type:** ROLLOUT SAFETY.
**Severity:** MEDIUM (procedural).

1. **PERF-001 before everything.** Every other finding in this report is a
   regression that a working gate would have to catch. PERF-012's re-baseline
   ("with the dead task removed, the p95 will be materially worse than today's
   number") is *unobservable* until the gate can report a real p95. Land the
   `get_response_time_percentile` fix and remove the dead `awk` **first**; only
   then re-baseline.
2. **PERF-006 #1 + PERF-010 touch the same contract.** Both change the
   producer/consumer relationship of `cached_ids` in the same view. They are
   individually compatible but must land as one change with one test, or the
   second will be written against the first's assumption. If PERF-006 #2 also
   lands, add a rendered-page assertion on the truncation notice.
3. **PERF-011's new alert depends on ENT-001.** `prometheus-slo-alerts.yaml:13-16`
   documents that counter-based alerts are untrustworthy under per-worker
   metrics. A new latency alert added before ENT-001's `child_exit` guard ships
   inherits the same defect. Sequence after (or with) ENT-001.
4. **PERF-004 + PERF-009 + PERF-014 are one change.** Fixing the trust-badge
   fallback and the header `.exists()` N+1 changes the real query inventory;
   only then is there a defensible number to put in `_QUERY_BOUND`, and only then
   is the corrected comment accurate. Fixing the comment first would publish a
   number nobody measured.

**No circular dependencies were found.** Two rejected recommendations
(PERF-006 #3 `work_mem`, PERF-011 #2 `workers`) would each have *created* a
dependency on work that does not exist, which is a further reason to reject them.

---

## Methodology Gaps

The auditor's caveat list is honest, well-scoped, and materially better than
average — the locmem-vs-Redis distinction, the explicit refusal to file a
speculative connection-pool problem, and the per-finding volume disclosure are
all correct and all load-bearing. Seven items are nonetheless missing:

1. **The worker/concurrency model is not in the caveat list at all.** Every
   measurement is single-request, single-worker. `workers = 3` × `sync` and the
   shipped `WEB_CPUS = 1.5` bound every conclusion about throughput — and are the
   reason PERF-011's capacity half is rejected.
2. **`DEBUG=1` is disclosed, but its consequence is not.** Template compilation
   is a per-process, first-request-only cost. The report's 586 ms "cold template
   compile" and 420 ms "warm" are **not two samples of the same thing**, so the
   35 % cache improvement it derives from them is not a like-for-like
   comparison.
3. **The write path was measured single-connection with no concurrency.** 2.54
   ms/statement cannot be decomposed into round-trip versus write cost without a
   second measurement. This is why PERF-003's "305 s → a few seconds" is not
   accepted as a projection.
4. **No `EXPLAIN` excerpt for the plan the fix targets.** PERF-002 asserts
   "nested-loop joins with a `Memoize` node over `ad_features`, stacked one per
   feature" in prose, and the whole row-count-multiplication argument — and the
   promise that a composite join yields a constant-shape plan — depend on that
   plan shape actually being produced. A plan excerpt would make the fix's benefit
   verifiable rather than asserted.
5. **`PROMETHEUS_MULTIPROC_DIR` is not set in the probe environment**, so the
   metrics path was never exercised and no alert could have been validated.
6. **`work_mem` and `max_connections` were not reported**, even though raising
   `work_mem` is one of the three proposed fixes. Confirmed baseline: `work_mem =
   4MB`, `max_connections = 100`, `DB_CPUS = 2.0`, `DB_MEM_LIMIT = 1g`,
   `WEB_CPUS = 1.5`, `WEB_MEM_LIMIT = 512m`, `SCHEDULER_CPUS = 0.5` — none of
   which is overridden in any `.env.*` file.
7. **The probe container had no memory limit** (`HostConfig.Memory = 0`, per the
   report's own text), which is *why* its OOM required the host to be exhausted.
   On the shipped 1 GB `DB_MEM_LIMIT` the same query behaves differently. The
   report notes the OOM "may not happen" on a real budget; it does not note that
   its own 60 000-row dataset build is what made the host the limiting factor.

**A production-load re-test must cover** the real `WEB_CPUS` / `WEB_MEM_LIMIT` /
`DB_CPUS` / `DB_MEM_LIMIT` allocation (not an unlimited container);
**Redis**, not locmem, for cache *latency* — the report is right that only
hit/miss control flow and statement sizes survive locmem; **nginx in front**
(TLS, gzip, `worker_processes`, `limit_req`) since the byte figures in PERF-008
and PERF-006 are pre-compression; a **representative term-frequency
distribution** rather than one term chosen to match 14 194 rows; a **city list at
the real size** (the shipped 15 rows are not a country); **`PROMETHEUS_MULTIPROC_DIR`
set** so the alerts are trustworthy; and — the precondition for all of it — a
**corrected locust gate whose measured p95 is the number that gates the build**.

---

## Volume Dependence: what survives at production-realistic scale

**Survives unchanged (shape or configuration is the finding, not the timing):**
PERF-001 (config + API drift), PERF-003 (N+1 write loop; cost is linear in active
ads), PERF-004 (conditional only on the trust row being absent), PERF-005
(linear in active saved searches), PERF-007 (bounded at 3 concurrent), PERF-009
(7 roots × 2 sites on the shipped catalog), PERF-010 (bounded by the 1 000 cap),
PERF-011 observability (config), PERF-012 (URLs and coverage), PERF-013 (125
statements at 60 k, unscheduled), PERF-014 and PERF-015 (documentation).

**Survives conditionally — the defect is real, the magnitude is not:**
PERF-006 fixes #1 and #2 (they apply only to queries with ≥1 000 matches, which
the CI load test can never produce); PERF-008 (real at a real country list,
immaterial at 15); PERF-002 (the *shape* survives; the absolute milliseconds and
the OOM are environment-specific — I reproduced the OOM on a 700 MB container,
and a 1 GB production container is plausible but was not measured).

**Does not survive as stated:**

- **PERF-006's "warm search is 510 ms, breaching the 500 ms p95 SLO."** One
  sample, `DEBUG=1`, synthetic 60 k rows, a term chosen to match 14 194 rows, DB
  co-located, no TLS/gzip. The CI load test seeds **120** ads; at that volume the
  query is trivially fast. This cannot be a HIGH.
- **PERF-008's 2.9 MB page and 61 ms query.** `cities.json` ships **15** records.
  The 5 015 rows were injected to expose scaling. Today's cost is ~8 KB / ~0.2 ms.
- **PERF-011's "~7.1 req/s".** A ratio for reasoning, not a capacity plan — and
  the binding constraint is the 1.5-CPU quota, not `workers`. A capacity number
  computed without the quota is not a capacity number.
- **PERF-002's `COUNT(*)` millisecond table.** Same synthetic dataset, and the
  60-feature row is literally "backend killed" rather than a measurement.

**Explicitly not reproducible in this environment:** the auditor's 60 000-ad
dataset, its 14 194-match FTS term, its 5 015-city table, its Redis behaviour, and
any absolute latency on real hardware. Every conclusion above rests on query
shape, statement size, parameter count, query count, call frequency, lock-hold
time, and deployed configuration — all of which were independently re-derived
here.

---

## Rollout Analysis

| # | Action | Depends on | Risk | Backward-compatible? |
|---|---|---|---|---|
| 1 | Fix `_assert_p95` → `get_response_time_percentile(0.95)`; delete the dead `awk`; add a hook unit test | — | **Low.** The job is red today; a working gate can only improve the signal. The first green run may legitimately be red on latency. | Yes |
| 2 | `DB-004`: set `statement_timeout` / `lock_timeout` | Co-ords with `SRCH-001`; every long-running command must be re-checked against the chosen value | **Med.** A too-low `statement_timeout` silently truncates legitimate work (`send_alerts`, `recompute_normalized_prices`, the FTS count). Choose per-role, and re-baseline after. | Yes, if per-role |
| 3 | `SRCH-001` + the composite-join remediation | 2 (ideally) | **Med.** `distinct()` → grouped-`Count` is a semantic change; AND-of-features must be proven equivalent by test. A cap alone leaves a bounded-but-still-quadratic plan. | Yes, with a test |
| 4 | Correct the two locust URLs; assert 0 % failures | 1 | **Low.** The p95 will get worse — that is the intended discovery. | Yes |
| 5 | PERF-006 fix #1 + PERF-010, as **one** change with one test | — | **Low.** Both are local; combine because both change `cached_ids`. | Yes |
| 6 | PERF-006 fix #2 (return `SEARCH_CACHE_MAX_HITS + 1`) | 5 | **Med — user-visible.** The displayed count stops being the true total. Needs a product decision and a rendered-page assertion on the truncation notice. | **No** (displayed value changes) |
| 7 | PERF-004 + PERF-009 fixes, then derive `_QUERY_BOUND` from the measured inventory and correct its comment | — | **Low.** | Yes |
| 8 | PERF-011 alert scope | **ENT-001** (or with it) | **Low** in YAML, but an untrustworthy alert is worse than none until ENT-001 lands. | Yes |
| 9 | PERF-003 `bulk_create(update_conflicts=True)` | — | **Low.** The `uq_daily_ad_metrics_ad_date` constraint is verified present. Measure before/after; do not promise a number. | Yes |
| 10 | PERF-005 loop grouping + progress logging | — | **Med.** Grouping by `(language, query)` changes result-set construction; intersection in Python must preserve per-search structural filters and the 10-per-digest cap. | Yes, with a test |
| 11 | PERF-008 — remove the duplicate `save_search_cities` only | — | **Low.** | Yes |
| 12 | `profile_queries`: `--min-rows`, real shapes, resolved ids, nightly job | 4 (re-baseline) | **Low.** The nightly job seeds 20 k rows — budget it; do not put it on every PR. | Yes |
| 13 | PERF-013, PERF-014, PERF-015 — ride along with 7 and 12 | 7, 12 | **Low.** Documentation and test-guard corrections. | Yes |

**Explicitly not on this list, and why:** raising `work_mem` (PERF-006 #3) and
raising `workers` (PERF-011 #2) — both rejected above. Both would have created
dependencies on work that does not exist, and the first is a measurable risk of
turning a bounded request into an immediate container OOM.

---

## Required Fixes

**Mandatory — P0**

1. **PERF-001 — make the p95 gate real.** `p95 = stats.get("Total").get_response_time_percentile(0.95)`
   in `src/benchmark/locustfile.py:37`; delete the dead `awk` block at
   `.github/workflows/ci.yml:499-506`; add a test that builds a `StatsCSV` from a
   synthetic `StatsEntry` and asserts the hook extracts a p95 (this is the only
   thing that would have caught the `uv.lock` bump). Assert a non-empty parsed
   value in CI so a future locust format change fails loudly.
2. **SRCH-001 + PERF-002 — bound the input *and* collapse the join.** `max_length`
   on `ListingsQueryParams.feature_slugs` with truncation in
   `ListingsQuery.build_queryset`, plus the single composite `slug__in` + filtered
   `Count` join. The composite join is what makes the plan constant-shape; the cap
   alone does not.
3. **DB-004 — set `statement_timeout` and `lock_timeout`**, per role, sized
   against the longest legitimate scheduled command. VAL-001 makes this
   co-equal with SRCH-001: the recovery term is unbounded from the application.

**Mandatory — P1**

4. **PERF-012a — fix the two locust URLs** (`/category/electronics/`,
   `/category/electronics/phones/`) and assert a 0 % failure rate in the CI step.
   Re-baseline the p95 afterwards, **after** fix 1.
5. **PERF-006 #1 + PERF-010 — one change, one test.** Push `[:1000]` into SQL;
   slice the `Case/When` arms to the page.
6. **PERF-004 + PERF-009 — fix both N+1s.** `getattr(user, "trust_score", None)`
   with the `.get()` fallback and the false comment deleted; `has_children=Exists(…)`
   annotation with `{% if cat.has_children %}` at `header_catalog.html:108,199`.
   **Do not** apply the `prefetch_related("children")` fix from the report — it is
   a no-op against `mptt`'s `get_children`.
7. **PERF-011 (observability) — extend the latency SLO alerts beyond
   `handler="search:search"`** to cover `ads:listings`, after or with ENT-001.
8. **PERF-003 — replace the upsert loop with
   `bulk_create(update_conflicts=True, unique_fields=["ad","date"])`**, and
   measure before/after rather than projecting a runtime.

**Mandatory — P2**

9. **PERF-005 — group the daily alert loop by distinct `(language, query)`** and
   add per-search progress logging; batch the notification writes (the daily path
   is already batched; the immediate-alert path is not).
10. **PERF-006 #2 — decide the truncated-count UX explicitly**, then implement
    `SEARCH_CACHE_MAX_HITS + 1` + `results_truncated`, with a rendered-page
    assertion on the notice.
11. **PERF-012b/015 — `profile_queries`: add `--min-rows`, add the missing
    production shapes, replace the hard-coded `city_id=1` / `category_id__in=[1,2,3]`
    with resolved ids, add a nightly job.**
12. **VAL-002 — correct the six non-existent quotations in
    `.ai/audit/13-performance/findings.md`** before the report is used to
    schedule work.

**Mandatory — P3**

13. **PERF-008 — remove the duplicate `save_search_cities` at `search.py:217`.**
    Cache the header list **only** after the city data source is decided.
14. **PERF-014/015 — correct the `images` sentence in
    `test_search_query_count.py`, derive `_QUERY_BOUND` from the measured post-fix
    inventory, and soften `docs/ops/profiling.md`'s "best signal" wording plus its
    false `make up` claim at `:100`.**

---

## Advisory Recommendations

1. **Adopt VAL-003's rule as a phase-wide standard:** a single-request timing is
   a smoke measurement. It may say "right order of magnitude"; it may not say
   "breaches a percentile SLO". Two findings in this report already turned on it.
2. **Add a dependency-drift gate for benchmark tooling.** PERF-001's root cause
   is a silent API change in a dev dependency. The locust hook needs a unit test
   for the same reason `test_i18n_completeness.py` exists: a format change should
   fail loudly, not silently disable a gate.
3. **Sequence `SRCH-001` and `DB-004` together.** They are the same failure seen
   from two angles, and either alone leaves the outage unbounded.
4. **Consider making `WEB_CPUS` / `WEB_MEM_LIMIT` / `DB_CPUS` / `DB_MEM_LIMIT`
   explicit in `.env.prod.example`.** Four variables that silently default to
   1.5 CPU / 512 MB / 2.0 CPU / 1 GB in *every* shipped environment are load-bearing
   for capacity, for memory, and for this report's severities. Writing them out
   costs nothing and makes the deployment target reviewable.
5. **Re-file the `find_matching_saved_searches` fan-out with its trigger, not as a
   latent note.** The report is right that `IMMEDIATE_ALERTS_ENABLED` is default-off
   and that it was not reproduced enabled. A finding that activates on a flag flip
   belongs on a watch list tied to the flag, so it is not rediscovered from scratch
   when someone enables it.
6. **PERF-007 option 1 is worth taking opportunistically, not as a P1** — and its
   justification should be "improve the cold-miss path", not "the lock is not a
   stampede guard" (it is, on the stale path).
7. **Re-verify the phase-13 report's millisecond figures against a real term
   distribution** before any of them are quoted externally. The *shapes* are sound
   and hardware-independent; the numbers are not.

---

## Closing Assessment

The auditor did the hard part correctly: it refused to accept the previous
cycle's pre-declared "RESOLVED" verdicts, it built an isolated dataset instead of
hammering the shared database, it verified the FTS trigger's presence before
trusting any FTS result, it explicitly declined to file a speculative
connection-pool problem, and it disclosed its volume dependence per finding. Those
are the marks of a careful audit, and 5 of 15 findings survive validation
completely intact.

What it got wrong clusters into three groups, and none of them is a bad-faith
problem. First, **it graded its own headline gate backwards**: it found a real
defect in dead shell code, noticed that the *effective* gate was working, and
then carried the dead code's failure mode into the title, the severity and the
impact while correctly describing the working gate in a subordinate paragraph.
Second, **it filled gaps in its own evidence with plausible-looking
reconstruction** — six quotations, file paths and function names that do not
exist (VAL-002). Third, **it let synthetic volume do the work of measurement**,
which inflated PERF-004, PERF-006 and PERF-008 to HIGH and would have inflated
PERF-008's city table straight to a P0 if the numbers had not been checked
against the shipped fixture.

The two recommendations that would have done real harm — raise `work_mem`
server-wide on a 1 GB database container shared by three processes, and raise the
gunicorn worker count on a 1.5-CPU allocation for a 74 %-CPU-bound workload — are
exactly the recommendations that a synthetic benchmark with no deployment context
produces. Both are rejected here with the configuration evidence that refutes
them.

**Net: 0 CRITICAL · 2 HIGH · 8 MEDIUM · 5 LOW, with no finding requiring an
architectural change.** The performance posture of this project is better than the
source report implies and worse than its "genuinely well-implemented" section
suggests: the cache invalidation really is correct and the index coverage really
is good, but the load test that is supposed to protect all of it is broken in two
directions at once, and the one input that can take the database offline is
still unbounded. Fix the gate first, then the input bound, then the cheap wins.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 5 | PERF-010, PERF-012, PERF-013, and (with mechanism notes) PERF-002 → merged, PERF-009 → content kept |
| Reclassified / adjusted | 9 | PERF-001, PERF-003, PERF-004, PERF-005, PERF-006, PERF-007, PERF-008, PERF-011, PERF-014, PERF-015 |
| Merged | 1 | PERF-002 → SRCH-001 (CRITICAL) |
| Rejected | 0 whole findings | 2 *recommendations* rejected: PERF-006 #3 (`work_mem`), PERF-011 #2 (`workers`) |
| VAL- (cross-phase / rollout / input integrity) | 4 | VAL-001, VAL-002, VAL-003, VAL-004 |

### Rejected Recommendations

| Origin | Recommendation | Reason |
|---|---|---|
| PERF-006 #3 | Raise `work_mem` to 32–64 MB for web/scheduler | `work_mem` is per-node × per-worker × per-connection. Against `DB_MEM_LIMIT=1g` (unset in every `.env.*`) and `max_connections=100`, and on the very `?features=` plan that needs one hash node per feature, this converts a bounded slow request into an immediate container OOM. Also **unnecessary**: fix #1 removes the only spilling node in the path. |
| PERF-011 #2 | Make `workers` env-driven and set it "near the core count" | `web` ships with `cpus: ${WEB_CPUS:-1.5}` / `mem_limit: ${WEB_MEM_LIMIT:-512m}`, neither overridden. The core count *is* 1.5, so the recommendation means 1–2 workers — fewer than today — on a 74 %-CPU-bound workload. The throughput ceiling is a property of the host allocation, not of `gunicorn.conf.py`. |
| PERF-009 fix | `prefetch_related("children")` on the `root_categories` queryset | **Would not work.** `mptt.models.MPTTModel.get_children` builds a fresh queryset via `_mptt_filter(parent=self)` and reads only `self._cached_children`; it never consults `_prefetched_objects_cache`. A no-op that would ship as a "fix". Corrected to an `Exists` annotation. |

### Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-------------|-----------|
| PERF-002 | **SRCH-001** (phase 08, CRITICAL) | Same code path, same defect, same failure mode, same fix family. Phase 13's plan-shape grading and composite-join remediation are **new supporting evidence** and are retained on SRCH-001; the `?features=` input bound and the join collapse are now two halves of one P0 item. |

### Reclassified Findings

| ID | Original severity | Validated severity | Rationale |
|----|-------------------|--------------------|-----------|
| PERF-001 | CRITICAL | **HIGH** | The report's own CRITICAL band requires regressions to be *silent*; they are not — the `load-test` step exits 2 on every run because `_assert_p95` calls `StatsEntry.percentile(0.95)`, which takes no argument in locust 2.46.6. A permanently-red gate destroys signal rather than manufacturing false reassurance, and the correct fix is completely different. |
| PERF-003 | HIGH | **HIGH** (attribution corrected) | The N+1 write loop, the 305 s single transaction, the advisory-lock hold and the `bulk_create(update_conflicts=True)` fix are all verified; the *cause* ("pure per-statement overhead") is not, and the "→ a few seconds" projection must be replaced by a measurement. |
| PERF-004 | HIGH | **MEDIUM** | Mechanism fully confirmed, but the cost is ~24 indexed `SELECT`s **only when the trust row is absent** — 5–10 ms on a ~420 ms page, on a path that already prefetches correctly. |
| PERF-005 | HIGH | **MEDIUM** | Structure confirmed; the cost is linear and reaches ~10 % of the scheduler's own 1 800 s timeout at 1 000 saved searches, on a 0.5-CPU container. The "secondary cost" is misattributed to this path (it is already batched here). |
| PERF-006 | HIGH | **MEDIUM** | The count-bypass defect is confirmed exactly; the HIGH rested on a single `DEBUG=1` sample on synthetic data — the same fallacy the report criticises in PERF-012c. Fix #3 additionally **rejected**. |
| PERF-007 | MEDIUM | **LOW** | True on the cold-miss path only; the stale-window path is a correct stampede guard. The `default`-and-fall-back contract is documented three times and is an intentional latency-over-DB-load trade. |
| PERF-008 | MEDIUM | **MEDIUM** (ROI gated) | Design property confirmed at three sites, but the shipped `cities.json` is 15 records (~8 KB, ~0.2 ms). Only the duplicate `save_search_cities` has positive ROI now; the cache must wait on a city-data-source decision. |
| PERF-011 | MEDIUM | **MEDIUM** (observability only) | The SLO alert-scope gap is real and free to close. The capacity half is rejected: `WEB_CPUS=1.5` / `WEB_MEM_LIMIT=512m` ship as defaults, and the workload is 74 % CPU-bound. |
| PERF-014 | LOW | **LOW** (content corrected) | The quoted comment does not exist; the real one names both N+1s and prescribes the fix. Only the `images` sentence is genuinely false. |
| PERF-015 | LOW | **LOW** (claim 1 refuted) | `make profile` runs `scripts/profile_search.py`, not `profile_queries`; the doc documents two tools and correctly states the 10 k skip. The coverage gap and the wrong-axis threshold are the real content. |

### Checkpoints

#### Checkpoint 1 — Auditor analysis

- **Stage:** Auditor analysis
- **Findings in scope:** 15 (1 CRITICAL, 5 HIGH, 6 MEDIUM, 3 LOW)
- **Evidence anchor:** `.ai/audit/13-performance/findings.md`, self-contained; all evidence quoted inline
- **Dependencies / blockers:** none
- **Checkpoint status:** closed

#### Checkpoint 2 — Researcher verification

- **Stage:** Researcher verification
- **Findings in scope:** 15
- **Cross-phase conflicts:** 0 (one discrepancy, **resolved** — VAL-001: 30 s = time-to-kill, >200 s = WAL-redo recovery window; decomposed as 12.00 s / 8.00 s / 20.00 s on an isolated PG 18.6)
- **Merge candidates:** 1 (**PERF-002 → SRCH-001**, accepted)
- **Evidence-integrity defects:** 6 non-existent quotations (VAL-002)
- **Dependencies / blockers:** none
- **Checkpoint status:** closed

#### Checkpoint 3 — Per-finding validation

- **Stage:** Per-finding validation
- **Findings in scope:** 15
- **Decisions:** 5 CONFIRMED · 9 ADJUSTED · 1 MERGED · 0 REJECTED (2 recommendations + 1 remediation rejected)
- **New defects found inside existing findings:** 1 (`StatsEntry.percentile()` API break in `_assert_p95`)
- **Cross-finding inconsistencies:** 1 (VAL-003 — single-sample-as-percentile)
- **Rollout-safety issues:** 4 (VAL-004)
- **Checkpoint status:** closed

#### Checkpoint 4 — Final consistency audit

- **Stage:** Final audit
- **Pipeline integrity:** OK. All four stage gates closed. The report is self-contained: every finding, verdict, severity and fix is stated here, with no dependence on the source report or on any live source-file read.
- **No source file was modified.** Probe container and all probe artefacts destroyed; the shared test database was never written to.
- **Checkpoint status:** closed
