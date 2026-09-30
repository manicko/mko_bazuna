---
plan_id: "11-test-coverage-remediation"
phase: "11"
phase_name: "Test Coverage & Test Suite Quality"
source_report: ".ai/audit/99-validation/11-test-coverage-validated-findings.md"
date: "2026-09-29"
planner: "Planner (subagent)"
anchor_commit: "6413df5"
report_anchor_commit: "9e96b84"
status: "planned"
findings_in_scope: 16
findings_still_present: 14
findings_already_fixed: 1
findings_stale_count: 1
findings_rejected: 0
blocks: 16
---

# Execution Plan — Phase 11 Remediation (Test Coverage & Test Suite Quality)

## 0. Header, provenance and scope statement

### 0.1 Provenance

| Item | Value |
|---|---|
| Source report | `.ai/audit/99-validation/11-test-coverage-validated-findings.md` (validated, 1261 lines) — the **only** surviving phase-11 input |
| Source findings file | `.ai/audit/11-test-coverage/findings.md` — **deleted from the working tree** (verified). Recorded for traceability only; **not** an input, and **not** a problem to fix. No block may restore it |
| Report anchor commit | `9e96b84` |
| Report's *own* anchor | `0c91666` — **does not exist in the repository** (`11-VAL-001`, confirmed and re-confirmed at this anchor) |
| Code-context document | `.ai/tmp/code-context-phase11.md` (986 lines, Auditor) |
| **Working anchor commit for this plan** | **`6413df5`** (`git rev-parse --short HEAD`, taken before writing) |
| Date | 2026-09-29 |
| Findings in scope | 16 — `11-TEST-001` … `11-TEST-014` plus `11-VAL-001` and `11-VAL-002` |
| State at the anchor | **14 still present · 1 already fixed (`11-TEST-013`) · 1 stale in its count (`11-TEST-001`) · 0 rejected** |
| Validated severity split | **CRITICAL 0 · HIGH 3** (`11-TEST-002`, `11-TEST-003`, `11-TEST-004`) **· MEDIUM 10 · LOW 0** |
| Execution blocks | **16** — 3 `reconciliation`, 6 `configuration`, 7 `coverage` (BLOCK 1 is the deliverable) |
| Implementor concurrency | **1**, strictly sequential (project rule: one implementor at a time) |
| Migration | **none shipped.** `11-TEST-007`'s `UniqueConstraint` is phase 08's; `11-TEST-003`'s bound is a test-settings option, not a schema change |

**This phase's central job is reconciliation, not new tests.** Nine of the sixteen blocks
either repair the *harness* that measures the suite or produce a *schedule* other phases'
plans can be checked against. Only six blocks add a test, and three of those six cannot
land until a production change in another phase has landed.

**The deliverable is BLOCK 1's output — the ordered test-change schedule** (§4.1, §4.4
and §5.1 together). Four test files are claimed by more than one phase; `src/backend/conftest.py`
is claimed by one phase and forbidden to seven. Until BLOCK 1 is closed, the rest of this
plan — and phases 03, 05, 06, 07, 08 and 10 — have no shared ordering for those artefacts.

**Naming convention.** Every citation of this phase's own findings is cycle-scoped
**`11-TEST-0NN`** (and **`11-VAL-0NN`**), never a bare `TEST-0NN`, wherever it must survive
into a comment, a docstring, a tracker entry or a commit message. The `TST-001`…`TST-005`
markers that already exist as in-source provenance markers in shipped code are **not** this
phase's vocabulary and must not be written, extended or swept by any block.

---

### 0.2 Evidence basis — read this before executing any block

The validated report is the narrative source; the Auditor's code context re-measured it
against the tree at `6413df5`; this Planner independently re-verified the load-bearing
claims below. **The tree is the authority.** Where the report and the tree disagree, the
correction is here and the plan is built on the tree's answer.

**No test suite was run for the audit, for the code context, or for this plan.** Every
count below is `ast`/regex/file-read or a host-side linter run that needs no database.

#### 0.2.1 Corrections — the tree wins

| # | Claim | Report says | **Tree at `6413df5` says** | Consequence |
|---|---|---|---|---|
| **C-1** | `TEST-001`: `create_test_ad` call sites depending on the `ON_MODERATION` default | **111 in 19 files** (62 defaulted + 49 explicit) | **124 in 22 files** (62 defaulted + **62** explicit). ✔ Verified: `src/backend/conftest.py::create_test_ad` and `::create_test_ads_bulk` still declare `status: AdStatus = AdStatus.ON_MODERATION` — the *default* is unchanged, the *explicit* population grew by 13 in three files (`test_moderation_views.py` 13→14, `test_admin_actions.py` 12→14, `test_auto_moderation.py` 1→2) and four files appeared (`test_sweep_purge_failed.py` 4, `test_ad_constraints.py` 2, `test_trust_calculator.py` 2, `test_ad_lifecycle.py` 1) | The **defaulted count is stable at 62**, which is the number the mechanical pass actually touches. Use **124**, never 111. Corrected per-file table in §0.2.3 |
| **C-2** | `TEST-013`: `basedpyright .` returns errors | 12 errors in `src/backend` + 2 in `src/telegram_bot`, both exit 1 | **0 errors, exit 0, in both scopes; `ruff check src/` clean.** Verified by the Auditor on the host at this anchor and re-confirmed here | `11-TEST-013` is **CLOSED**, not remediated. Its item 2 (add a `basedpyright .` step for `src/telegram_bot`, move `ruff` to the repo root) survives as a separate CI-scope item **only if** phase 01's `lint`/`typecheck` block has not already done it — **Q12** |
| **C-3** | `TEST-002`: `ci.yml` runs pytest with a bare `--cov` from `src/backend` | confirmed | ✔ Confirmed at `ci.yml` — the pytest step carries `working-directory: src/backend` and `uv run pytest … --cov --cov-report=term --cov-report=xml` with no `--cov` value. **But the report missed a twin: `.github/workflows/ci-nightly.yml` carries the identical defect** (`--cov` with `working-directory: src/backend`) | **Fix both workflows or neither.** Phase 11 is the **first** phase to touch `ci-nightly.yml` — no other plan claims it |
| **C-4** | `TEST-014`: the media `transaction=True` surface that can observe MEDIA-001's callback | "the seven `test_sweep_*.py` files plus `test_ad_image_delete_signal.py`" | **2 files / 7 tests.** `apps/core/tests/test_ad_image_delete_signal.py` (3 tests, class decorator on `TestAdImageDeleteSignal`) and `apps/core/tests/test_delete_photo_single_call.py` (4 tests, module `pytestmark`). `apps/media/tests/test_sweep_orphaned_media.py` is **transactional** (`pytestmark = [django_db, integration]`), so the `on_commit` callback never fires there | **`11-TEST-014` is worse than stated, and the media blast radius of a refcount bug inside the callback is 7 tests, not a sweep surface.** BLOCK 7 |
| **C-5** | `TEST-010`: the 27 `inspect.getsource` sites | 27 across 8 files; per-file table | **27 across 8 files reproduced exactly** — but **two paths are misattributed**: `test_unsubscribe.py` is in `src/telegram_bot/tests/`, not `apps/users/tests/`; `test_recompute_command.py` is in `apps/currencies/tests/`, not `apps/ads/tests/` | Use the tree's table (§0.2.3). A test written against the report's path would target a file that does not contain the assertion |
| **C-6** | `TEST-008`: "the seed is persisted in `.pytest_cache/v/cache/randomly_seed` and reused on re-runs, so local reproduction is already possible" | local replay already works | **The file does not exist in this working tree.** `.pytest_cache/v/cache/` holds only `lastfailed` and `nodeids`. The plugin's cache read is real; the cache entry is not there | Local seed replay does **not** work today. The finding survives in full — including a mitigation the report did not have to argue for. BLOCK 4 |
| **C-7** | `TEST-011`: "both named target migrations are absent" (squash migration, search-vector backfill) | absent | **Half wrong.** The `apps/core/management/commands/squash_rehydrate_runsql.py` **command exists and is fully tested** (4 tests). What does not exist is a *squash migration file*; the search vector is maintained by a PostgreSQL trigger, never a `RunPython` backfill. The four real `RunPython`/`RunSQL` data-migration targets the report then listed **are** present | BLOCK 13 targets the four real migrations. **A test written against "squash rehydrate" as a *migration* would test nothing** |
| **C-8** | `VAL-001`: the report's anchor `0c91666` does not exist | confirmed | **Confirmed and worse.** `0c91666` is still unresolvable, and fourteen further citations/claims have drifted between `9e96b84` and `6413df5` — including three of the report's own **re-measured** numbers (C-1, C-2, C-4) | Every count that carries remediation weight is **re-measured at execution time**. BLOCK 1 is the block that re-measures |
| **C-9** | Phase 05 BLOCK 4 finding 1: "`src/telegram_bot/tests/conftest.py` **redefines** `create_test_ad` and `create_test_ads_bulk` … bot tests **cannot** import the backend conftest … both conftests must change together. This is a **hard** requirement" | both conftests must change in the same commit | **Refuted.** The bot conftest does **not** redefine the factories — its own docstring (lines 79–80) says so: *"`create_test_ad` IS shared: it is imported from the backend conftest via `from conftest import create_test_ad` (resolved through `pythonpath`)"*. It **does** fully redefine the eight *fixtures* (`bot`, `dp`, `user`, `login_token_factory`, `seller`, `category`, `city`, `_clear_cache_between_tests` plus two reapers) because pytest's upward conftest discovery never passes through `src/backend/` from `src/telegram_bot/` | **One default change in `src/backend/conftest.py` reaches both trees.** Phase 05's "hard requirement" is wrong, and acting on it would edit a file that does not need editing. BLOCK 14 must not inherit it |
| **C-10** | Phase 11 code context §7 row 1: "`src/backend/conftest.py` — phase 11 does not currently own this file" | — | **Still true at this anchor.** Phase 05 BLOCK 4 claims it for exactly `11-TEST-001`'s change; phases 03 ("must not edit it at all"), 06, 07, 08, 09, 10 each state "**Nobody in this plan**"; phase 04 §6.2.8 forbids fixture reshaping outright. **Seven plans forbid it, one claims it, and this plan needs it** | **Q1 is a blocker.** BLOCK 14 does not start until it is answered. BLOCK 1 is where the answer is recorded |

#### 0.2.2 The census this plan carries forward — do not re-derive it, do not re-measure it casually

| Item | Value at `6413df5` |
|---|---|
| Test files | **213** (`test_*.py` under `src/`) |
| Test functions | **2 403** (`def test_*` / `async def test_*`, AST count — **not** collected items) |
| `Test*` classes | **456** |
| Backend apps | 163 files / 1 946 functions / 365 classes (14 apps; `core` 58/574, `ads` 38/424 are the two largest) |
| Settings modules | 9 files / 58 functions / 0 classes |
| Root infra | 8 files / 98 functions / 5 classes |
| Bot tree | 33 files / 301 functions / 86 classes |
| Fixtures | **24** across **6** conftests, **7** autouse. `src/telegram_bot/tests/conftest.py` **redefines** the fixtures (bot tests cannot import the backend conftest) but **shares** `create_test_ad` |
| `transaction=True` scopes | **48** in **39** files — bot 24, core 13, ads 3, moderation 3, users 3, currencies 1, search 1 |
| `TestCase` / `TransactionTestCase` / `captureOnCommitCallbacks` | **0 / 0 / 0** |
| `inspect.getsource` assertions | **27** across **8** files |
| Query-count-pinned files | **6** (19 `assertNumQueries` / `CaptureQueriesContext` sites) |
| Wall-clock SLO gates | **1** (`TestSearchResponseSLORegression`) |
| Registered markers | 8 — `unit`, `integration`, `seed`, `settings`, `concurrent`, `slow`, `real_images`, `xdist_group` |
| Skips / `skipif` / `xfail` | **0 anywhere.** Nothing is silently disabled; every test that exists is expected to run |

The report's `2 394 tests including the 190 bot tests` is a **collected-item** count at
`9e96b84`. Neither it nor the AST census is reproducible without a run; both are carried
forward as **static** measurements and are labelled as such in every block that uses them.

#### 0.2.3 Corrected per-file tables the blocks must use

**`create_test_ad` / `create_test_ads_bulk` sites resolving to `AdStatus.ON_MODERATION` — 124 in 22 files** (C-1):

| File | explicit | defaulted | total |
|---|---:|---:|---:|
| `apps/moderation/tests/test_priority_service.py` | 0 | 27 | 27 |
| `apps/moderation/tests/test_priority.py` | 0 | 24 | 24 |
| `apps/moderation/tests/test_moderation_views.py` | 14 | 1 | 15 |
| `apps/moderation/tests/test_admin_actions.py` | 14 | 0 | 14 |
| `apps/moderation/tests/test_auto_moderation.py` | 2 | 6 | 8 |
| `apps/moderation/tests/test_moderation_side_effects.py` | 5 | 0 | 5 |
| `apps/moderation/tests/test_approve_ad_side_effects.py` | 4 | 0 | 4 |
| `apps/core/tests/test_sweep_purge_failed.py` | 4 | 0 | 4 |
| `apps/analytics/tests/test_moderation_analytics.py` | 3 | 0 | 3 |
| `apps/moderation/tests/test_moderation_log.py` | 3 | 0 | 3 |
| `apps/currencies/tests/test_price_normalizer.py` | 0 | 3 | 3 |
| `apps/ads/tests/test_ad_constraints.py` | 2 | 0 | 2 |
| `apps/search/tests/test_search_view.py` | 2 | 0 | 2 |
| `apps/trust/tests/test_trust_calculator.py` | 2 | 0 | 2 |
| `apps/ads/tests/test_ad_lifecycle.py` | 1 | 0 | 1 |
| `apps/ads/tests/test_edit.py` | 1 | 0 | 1 |
| `apps/ads/tests/test_transition_concurrency.py` | 1 | 0 | 1 |
| `apps/core/tests/test_contact.py` | 1 | 0 | 1 |
| `apps/search/tests/test_search_cache.py` | 1 | 0 | 1 |
| `apps/users/tests/test_consent.py` | 1 | 0 | 1 |
| `apps/users/tests/test_deletion.py` | 1 | 0 | 1 |
| `src/telegram_bot/tests/test_ad_lifecycle.py` | 0 | 1 | 1 |
| **Total** | **62** | **62** | **124** |

Plus `src/backend/conftest.py` itself (the two defaults) — the 23rd file.

**`inspect.getsource` sites — 27 in 8 files** (C-5):

| File | Count |
|---|---:|
| `src/backend/apps/ads/tests/test_edit_views_locking.py` | 7 |
| `src/backend/apps/moderation/tests/test_admin_actions.py` | 5 |
| `src/backend/apps/core/tests/test_migrate_locked.py` | 4 |
| `src/backend/apps/users/tests/test_admin_pii_containment.py` | 4 |
| `src/backend/apps/moderation/tests/test_moderation_views.py` | 3 |
| **`src/telegram_bot/tests/test_unsubscribe.py`** | 2 |
| **`src/backend/apps/currencies/tests/test_recompute_command.py`** | 1 |
| `src/backend/apps/core/tests/test_sweep_archive.py` | 1 |

Plus three AST-source tests of a **different, defensible** shape (cross-tree invariants, not
substring matching): `apps/core/tests/test_advisory_lock_ids.py`, `apps/ads/tests/test_i18n_completeness.py`,
`apps/core/tests/test_squash_rehydrate_runsql.py`. And two structural source-inspection
tests that are not `getsource`: `apps/core/tests/test_sweep_lock_structure.py` and phase 05's
`TestBulkLockingStructure`.

#### 0.2.4 Runtime claims that are unverified, with the exact command to verify each

**Every one of these is carried into the evidence basis as unverified.** No block may cite
one as established fact, and no block may skip the verification because "the report already
established it" — the report did not run the suite either.

| # | Claim | Block | Verify with (Docker only — §1.1) |
|---|---|---|---|
| 1 | Any pass/fail baseline. The report's `2394 passed in 226 s` is **accepted as given** and is **not** comparable to the 2 403 AST function count | all | `$dc run --rm --env PYTEST_SKIP_MARKERS=seed test` |
| 2 | Collected-item count for the whole suite | 1 | `$dc run --rm -e PYTEST_OPTS="--collect-only -q --reuse-db" test` — note setting `PYTEST_OPTS` **replaces** the defaults, so `--reuse-db` must be added or the schema is rebuilt |
| 3 | Real branch-coverage percentage, and whether it clears `fail_under = 80` once the config actually loads | **2** | Run the CI command shape locally, or read the CI artifact. **This is `Q2`; BLOCK 2 does not start without it** |
| 4 | Query counts are currently **under** their bounds (`_QUERY_BOUND = 16` ad detail, `100` search, `_USER_SELECT_BOUND = 1` bot, two `<= 1` trust bounds) | 1, 9 | `$dc run --rm -e PYTEST_OPTS="-k test_ad_detail_queries or test_search_query_count or test_bot_query_count --reuse-db" test` |
| 5 | `TestSearchResponseSLORegression` passes against a live DB | 3, 9 | `$dc run --rm -e PYTEST_OPTS="-k TestSearchResponseSLORegression --reuse-db" test` |
| 6 | `PYTEST_OPTS` word-splitting behaviour | all | `$dc run --rm -e PYTEST_OPTS="-k \"a b\"" test` — expect the quotes to be word-split |
| 7 | A new `transaction=True` media scaffold actually fires the `on_commit` callback | **7** | The scaffold ships with its own positive control (§3, BLOCK 7). **A scaffold that looks right and never fires is worse than no scaffold** |
| 8 | `config/settings/test_migrations.py` is collected but contributes 0 tests | 13 | `$dc run --rm -e PYTEST_OPTS="--collect-only -q src/backend/config/settings/test_migrations.py --reuse-db" test` |
| 9 | Whether a chosen `statement_timeout` value trips `record_event`'s swallowed `OperationalError` | **5** | Read `record_event` and run the analytics tests after the bound lands. **This is `Q3`; BLOCK 5 does not start without DB-002 landed** |
| 10 | Whether the real coverage figure clears 80 % with `src/telegram_bot` in `source` and `branch = true` | **2** | Same as #3. **Fixing `ci.yml` alone and leaving `ci-nightly.yml` measuring the same inert configuration is a half-fix** |

**Never attempt the superlinear `?features=` reproduction against the shared instance.**
Phase 08's own probe terminated the PostgreSQL cluster twice; the report declines to carry
its `EXPLAIN`-only crash table forward and this plan declines to reproduce it. Phase 08's
independently-validated `ANALYZE` numbers are authoritative.

---

### 0.3 Scope statement (explicit)

**In scope — 16 finding-units.** 14 still present, 1 already fixed (`11-TEST-013`, closed —
C-2), 1 stale in its count (`11-TEST-001`, C-1), 0 rejected. Mapped onto 16 blocks in §2.

**In scope as *findings*, but narrowed by this plan's corrections** (each narrowing is
argued, not silent):

- `11-TEST-001` → **124 sites in 22 files**, not 111 in 19 (C-1); and the mechanical pass
  touches only the **62 defaulted** sites, which are stable across both anchors.
- `11-TEST-002` → **both** `ci.yml` and `ci-nightly.yml` (C-3). The report never mentions the
  nightly file.
- `11-TEST-003` → the **test-hosting half only**. The unbounded join loop is SRCH-001
  (phase 08, CRITICAL); the missing production bound is DB-004 (phase 03, HIGH). **Neither is
  re-filed.** This plan ships the test-side bound and the test itself.
- `11-TEST-005` → the **narrow** residual: no *behavioural* cross-process assertion and no
  *predicate-equality* test. The report's "zero tests cross the boundary" and its
  "threads cannot model two connections" are both refuted (at least five real cross-tree
  tests exist; `test_edit_views_locking.py` already exercises two independent transactions per
  thread). Its proposal 3 — do **not** run the real bot process inside pytest — is
  **endorsed**.
- `11-TEST-010` → **two paths corrected** (C-5) and the remediation is a **written rule**, not
  a blanket deletion: `test_migrate_locked.py::TestSessionLockLogging` is a `getsource` test
  that earns its place, and deleting all 27 would remove it.
- `11-TEST-011` → the **four real data migrations** (`ads/0003_dedup_per_user_drafts`,
  `search/0002_redact_search_queries`, `core/0003_add_bot_username`, `core/0002_seed_default`),
  and they must be exercised through the **subprocess shape** `apps/core/tests/test_migrations.py`
  already uses. A data-migration-effect test written in the default suite would silently pass
  for the wrong reason.
- `11-TEST-013` → **closed**. The remediation the report describes is a no-op. Only its item 2
  (CI lint/typecheck scope) survives, and only if phase 01 has not already done it (**Q12**).
- `11-TEST-014` → **worse than reported** (C-4): 2 files / 7 tests, not a sweep surface.

**Deliberately not in scope — see §6.** The brief-derived high-confidence zero-coverage
modules are **triaged, not tested**, in BLOCK 15; phase 10's two routed AST architecture rules
(`CQ-002`, `CQ-004`) are **refused** and recorded as refused; the `?features=` cap, the
`feature_slugs` bound and the `PopularSearch` `UniqueConstraint` are phase 08's; the
production `statement_timeout` is phase 03's; MEDIA-001's reference check is phase 07's; the
`AdvisoryLockId` enum is nobody's.

**One finding must not be revived under any name.** `ENT-004` (phase 01) is the *root cause*
of what `11-TEST-013` measured. The gate is green. Re-filing a red-typecheck remediation from
this phase would ship the same fix twice at a different severity — the same mistake `CQ-002` →
`ENT-005` already made once.

**No new test harness, no second conftest, no new test framework, no new fixture layer and no
new marker is proposed by any block.** The net new surface of this plan is: one committed
schedule artefact (BLOCK 1), four configuration edits, four CI-workflow edits, one settings
option, two doc corrections, and **eleven new test functions** across six files.

---

### 0.4 Severity corrections

The report's own movement is upheld in full and is **not** re-litigated: `TEST-001`
CRITICAL→HIGH, `TEST-005` HIGH→MEDIUM, the rest held. Post-measurement severities at this
anchor are **HIGH 3 · MEDIUM 10 · LOW 0**.

**Corrections this Planner makes to the *executed* risk, without re-grading the findings:**

- **`11-TEST-013` is closed, and its closure is itself a MEDIUM-risk item.** A finding that
  went from *red* to *green* between two anchors, with **no one editing the tests**, is a
  provenance question as much as a hygiene one. If the fix was the untyped `advisory_lock`
  context manager, it landed in **production** and the tests merely followed — which means a
  phase about to reintroduce that shape reintroduces a red gate. **Q12 must be answered
  before `11-TEST-013` is recorded closed in the tracker**, not after.
- **`11-TEST-002` executes as HIGH *risk*, not as a one-line change.** The report calls the
  remedy "one CI line" and effort S. That is true of the *edit* and false of the *effect*:
  the moment `[tool.coverage.report] fail_under = 80` starts being read, a gate that has
  never fired begins firing. **The edit is S; landing it safely is not.** BLOCK 2 is gated on
  measuring first.
- **`11-TEST-003` executes as MEDIUM–HIGH risk**, higher than the report's S/S. A
  `statement_timeout` in the test settings is a **global** change to every one of 2 403 test
  functions, and phase 03 recorded that `statement_timeout` produces an `OperationalError` on
  exactly the kind of INSERT `record_event` issues — which it currently swallows. **Landing a
  statement-level bound before DB-002 converts a swallowed error into a new failure mode in
  the analytics path.** That is a live hazard, not a theoretical one.
- **`11-TEST-009` is worse than the report's corrected version states.** The report corrected
  itself to "no `timeout-minutes` is configured on any job". Re-read against
  `ci-nightly.yml`: neither workflow bounds any job, and the nightly is unbounded too.
- **`11-TEST-001`'s severity does not change; its *scope* nearly halves.** Under the
  "make `ON_MODERATION` durable" branch of AD-008, the 62 defaulted sites become **correct**
  and the mechanical pass evaporates. Only the default flip and the two doc corrections
  survive. This is why BLOCK 14 is gated on **both** Q1 and Q2 rather than on Q1 alone.
- **`11-TEST-012` executes as S, lower than the report's M** — because the premise is
  refuted: `apps/core/tests/test_support_admin.py` already carries 12 registered-`ModelAdmin`
  introspection tests. The remedy is an **extension**, not a new module.

---

### 0.5 Open technical questions — resolved here, or explicitly gated in their block

**This plan does not choose where technical uncertainty exists.** Twelve questions are
carried forward from the code context plus six this Planner adds. Each produces either a
labelled **decision required before implementation** gate inside its block, with the options
and their consequences, or a named routing to the coordinator. **Silence is not an acceptable
outcome for any of them.**

| ID | Question | Block | Who decides | Status |
|---|---|---|---|---|
| **Q1** | **Who edits `src/backend/conftest.py`?** Phase 05 BLOCK 4 claims it for exactly `11-TEST-001`'s change; phases 03 ("must not edit it at all"), 06, 07, 08, 09, 10 say "**Nobody in this plan**"; phase 04 forbids fixture reshaping outright. Options in BLOCK 14 | **14** | **Coordinator** | **GATED — BLOCKER.** Seven plans forbid the file, one claims it, this plan needs it. Nothing in BLOCK 14 starts without this |
| **Q2** | **Has `AD-008` been decided, and which branch?** If `ON_MODERATION` becomes **durable** (auto-moderation defers to a human), all 62 defaulted sites become correct and the migration evaporates; only the default flip and the docs remain. If the durable state is **removed**, expectation flips land with the production change | **14** | Phase 05 owner + coordinator | **GATED — BLOCKER.** Phase 05's validator explicitly forbade taking the removal branch before `VAL-003` is resolved |
| **Q3** | **Test-side `statement_timeout`: what mechanism and what value?** `DATABASES["default"]["OPTIONS"] = {"options": "-c statement_timeout=N"}` vs a session-scoped `SET statement_timeout` + `RESET`. And must `N` equal DB-004's production value? `SET LOCAL` is a **no-op** outside a transaction block, so it is not an option for the 48 `transaction=True` scopes | **5** | Planner, with phase 03 sizing `DB-004` and `DB-002` landed | **GATED.** Two values drift silently; and `record_event` swallows the resulting `OperationalError` until DB-002 lands |
| **Q4** | **pytest-timeout shape and value.** A global `timeout` key, or a per-marker value with a larger global backstop? `timeout_method = "signal"` (interrupts the query) or `"thread"` (returns, leaves it running)? And `timeout-minutes` on the `test` and nightly jobs — 20? 30? The only wall-clock gate in the suite is `SEARCH_SLO_MS == 2000` and `test_lookup_cache_swr` sleeps `0.2` deliberately | **3** | Planner, with phase 13's latency surfaces in view | **GATED.** A `timeout_method` choice determines whether a runaway query is *killed* or merely *reported* |
| **Q5** | **Seed determinism: pin or record?** (a) pin `--randomly-seed` in `addopts` — deterministic, but **destroys shuffle detection**, which is the entire reason `pytest-randomly` is installed; (b) upload `.pytest_cache` as an CI artifact next to `coverage.xml` — keeps shuffling, records the seed; (c) both | **4** | Planner | **GATED.** Option (a) alone removes the plugin's reason for existing and can hide an order-dependence bug that is currently found on every run |
| **Q6** | **Who commits the hostile-`?features=` test?** Inside phase 08's `SRCH-001` commit (one commit: production cap + test), or as a phase-11 commit that is **red until phase 08 lands**? And in which file: `apps/ads/tests/test_features_filter.py` (AND-semantics, 3 requests, max 2 slugs) or `apps/search/tests/test_search_view.py` (phase 08 BLOCK 1's chosen home, 10 phase-08 blocks) | **6** | Planner + coordinator | **GATED.** A red-on-arrival commit is a rejected commit under the one-commit rule; a test that duplicates phase 08's own test is the duplication failure this plan exists to prevent |
| **Q7** | **Admin form/action contract scope.** Which registered `ModelAdmin`s form the data-subject set? Blanket rule vs explicit set — phase 06's **VAL-007 is mandatory**, because `test_support_admin.py` already asserts on `SupportContactAdmin.telegram_id` and a blanket data-subject rule false-positives on a support *channel* id. Assert **widget classes** (a `password` as `AdminTextInputWidget` fails) or **field-name sets** (an auto-built form exposes them, a declared one does not)? Is the rendered-page smoke test in scope? | **8** | Planner + phase 06 | **GATED.** A widget-class rule is the only one that can see AUT-005/PII-103; a field-name rule false-positives on every auto-built form |
| **Q8** | **What is the rule for the 27 `getsource` assertions?** (a) keep all; (b) keep the cross-tree invariants and the shipped regression guards, delete `test_admin_pii_containment.py`'s four substring assertions once BLOCK 8's contract tests cover them; (c) delete all 27 | **11** | Planner + Researcher | **GATED.** Option (c) deletes `test_migrate_locked.py::TestSessionLockLogging`, a shipped phase-01 hard regression guard, and the two `test_unsubscribe.py::TestResolveOwnedLocking` order assertions |
| **Q9** | **Data-migration effect tests: which of the four targets, and on what database?** `test_migration_repro` reuse or a new database? Does the subprocess shape need `MIGRATION_MODULES` unset for the target app only, or repo-wide? | **13** | Planner + Researcher, with phase 02 (which holds `test_migrations.py` via BLOCKs 3/4/5/9) | **GATED.** Running the forward migration against the main suite's `syncdb` schema would silently pass for the wrong reason |
| **Q10** | **Zero-coverage triage.** Disposition per module: write a test, mark as deliberately uncovered, or route. Specifically `src/backend/testing/moderation_fixtures.py` — unused **and** not coverage-omitted: **adopt it** (it may be the intended home for a moderation fixture nobody wired up) or **delete it**? And is `apps/cabinet/views/hub.py` (2 views, 0 references) worth two tests? | **15** | **Researcher**, then Planner | **GATED.** The dead-code policy says *investigate before proposing removal*, and this module has a plausible second life |
| **Q11** | **Should phase 11 build the two AST architecture rules phase 10 routed here** (`CQ-002`, `CQ-004`)? Phase 10's own reasoning is that *"a rule that must first be made true cannot be enforced before it is true"*, and both would false-positive on ~26 legitimate `AppConfig.ready()` deferrals | **15** | Planner | **GATED.** Phase 10's refusal is recorded in §6; the Implementor may not adopt or overturn it silently |
| **Q12** | **What actually fixed the typecheck gate?** `basedpyright .` is green in both scopes at this anchor and the report's 12+2 errors are gone. If the fix was the untyped `advisory_lock` context manager, it landed in production and `11-TEST-013`'s remediation is a no-op. If it was something else, a phase may be about to reintroduce it | **1** (records) · 16 (CI scope) | Auditor, from the commit log | **GATED, narrow.** Must be answered before `11-TEST-013` is recorded closed |

Additionally carried, not gated but **recorded**: `11-VAL-001` (the report's anchor does not
exist; fourteen further citations have drifted) and `11-VAL-002` (the "bare `TestCase`"
framing is inapplicable — zero `TestCase` subclasses; the exposure arrives through
`pytest.mark.django_db`). **Neither produces a source change.** `11-VAL-002` exists so that
the `on_commit` exposure is not double-counted between `11-TEST-004` and `11-TEST-014`, and
so that no downstream block is scoped against the wrong mechanism.

---

## 1. Environment and command contract for the implementor

**This environment is Windows 11 / PowerShell 7.** `make` requires WSL or GNU Make; use
`.\Makefile.ps1 <target>`. `head` / `tail` are unavailable in PowerShell.

### 1.1 Tests are Docker-only — `uv run pytest` on the host always fails

There is no PostgreSQL on `localhost:5432`. Every test run goes through the `test` service
of the `mko-bazuna-test` Compose project. `docker/entrypoint-test.sh` performs **no**
database setup: pytest-django provisions `test_mko_bazuna` itself under
`MIGRATION_MODULES = DisableMigrations()` (so the schema is built by **`syncdb`**), and the
session-autouse fixture `src/backend/conftest.py::_restore_test_schema_post_db_setup`
re-applies what `syncdb` cannot — `migrate --run-syncdb` → `load_exchange_rates` →
`setup_search_triggers` — under `AdvisoryLockId.TEST_SCHEMA_SETUP` (**111**).

```powershell
# Alias, copied once per session
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'

# Start the DB if it is not already up
docker ps --filter "name=mko-bazuna-test-db-"
$dc up -d db

# Fast gate (skips the nightly `seed` suite) — the default iteration command
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test

# Targeted run
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="-k test_name" test
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/test_edit.py --tb=short" test

# Full suite (only when the change touches seeding or images)
$dc run --rm test

# Fresh schema (only if a migration appears that phase 11 did not write — none should)
$dc run --rm --env PYTEST_OPTS="--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup" test
```

**Four caveats that will silently produce a wrong result if ignored:**

- `--env-file .env.test` is **required**; without it compose aborts on `${POSTGRES_*?}`
  interpolation. **Never** substitute the `mko-bazuna-dev` project name.
- `${PYTEST_OPTS:-...}` is **unquoted** in `docker/entrypoint-test.sh`, so every token is
  word-split on spaces. `-k test_name` and bare paths work; **quoted multi-token values do
  not** (`-k "a b"` splits into `-k`, `"a`, `b"`).
- Setting `PYTEST_OPTS` **replaces** the defaults
  (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`), so a
  targeted run loses `--reuse-db` *and* xdist parallelism. **Add `--reuse-db` explicitly to
  every targeted run in this plan**, or each one rebuilds the schema.
- **Never** use `--override-ini=addopts=` — it strips `--import-mode=importlib`, which
  `pyproject.toml` sets and which the `testpaths = ["src/backend", "src/telegram_bot"]`
  two-tree layout depends on.
- **Marker exclusion goes through `PYTEST_SKIP_MARKERS`, never `-m` inside `PYTEST_OPTS`.**

**Concurrent runs collide on the single `test_mko_bazuna` database.** Other phase agents are
running against the same instance. If a gate goes red while another agent is running,
**re-run it serially** before reporting it as a defect; the symptom is
`FATAL: database "test_mko_bazuna" does not exist` or `relation "..." does not exist`, not a
product failure. Prefer `.\Makefile.ps1 up | test | test-all | test-recreate | test-down` —
they manage the project name and env file for you.

### 1.2 Lint, typecheck, i18n

```powershell
uv run ruff check <path>            # lint
uv run ruff check --fix <path>      # auto-fix, INCLUDING import sorting (I001)
uv run basedpyright <path>          # typecheck
uv run djlint src/backend/templates/   # only if a template changes (no block does)
```

`[tool.ruff] fix = false` is set deliberately. **Scope `--fix` to the block's own files**;
a blanket `ruff check --fix src/` will reorder imports another phase's uncommitted work
depends on.

**Baseline at `6413df5`, verified on the host by the Auditor and re-confirmed here:**
`basedpyright .` from `src/backend` → **0 errors, exit 0**; from `src/telegram_bot` → **0
errors, exit 0**; `ruff check src/` → **All checks passed, exit 0**. Every block must leave
all three at that result. **No block in this plan adds a user-visible string**, so no block
touches `locale/*/LC_MESSAGES/django.po` and `test_i18n_completeness.py` is a **tripwire**
here, not a gate this plan changes.

### 1.3 Project rules the implementor must not negotiate

1. **English only.** Comments, docstrings, error messages, test names and commit bodies.
2. **No `print()`** — use `logger = logging.getLogger(__name__)`.
3. **Production code is king.** *If a test conflicts with architecture or business logic, fix
   or remove the test. Never distort production code for tests.* No block in this plan edits
   production code at all; the rule is restated because two blocks change **test
   expectations** (BLOCK 14's default flip, BLOCK 11's `getsource` rule) and it is the test
   that moves.
4. **Tests verify logic and component interaction, not trivial implementation details.**
   This is the standing judgement call on every block that adds a test, and it is why BLOCK
   8 asserts *widget classes and field contracts* rather than the current field list, and
   why BLOCK 11's rule exists at all.
5. **Django ORM is the persistence layer.** Pydantic v2 belongs at **system boundaries**
   (bot input, settings schemas, future API), not inside a test.
6. **Django 5.2 LTS `>=5.2.16,<6.0` · Python 3.14 · PostgreSQL 18 · aiogram 3.x.**
7. **All schema changes via Django migrations.** Phase 11 ships **none**; a migration
   appearing in any block is an automatic rejection of that block.
8. **Fixed values via `StrEnum`** — never plain strings or dicts.
9. **i18n is part of DoD** — `msgstr` non-empty for `ru` and `bs`. Vacuously satisfied here.
10. **Small, focused modules and functions.** No speculative abstraction. No scope creep.

### 1.4 One Implementor, strictly sequential, one commit per block

Only one implementor agent at a time. Every block is a single commit, staged by **explicit
path**:

```powershell
git add <specific-files>
git commit -m "{type}({scope}): {description}"
```

Commit-style examples from the repository: `fix(test): make fixtures idempotent for
--reuse-db`, `chore(agents) allow docker remove commands`. **Never** `git reset`,
`git checkout`, `git restore` or `git stash`; never rewrite history. Other agents are
committing in parallel — **changes you did not make are normal**, and `git status` will show
entries you do not own. Do not stage them. Do not revert them. Do not `git add .`.

**No commit without an explicit user request.** This plan is a plan; it does not commit.

### 1.5 The anti-pattern this phase must not produce

`11-TEST-010` is the standing example: **27 `inspect.getsource` substring assertions across 8
files** that pass whether the code works or is entirely broken, and fail on an equivalent
refactor. Every block that adds a test answers one question in its binding constraints:

> **If the production implementation were replaced by a different implementation with the
> same observable behaviour, would this test still pass?** If not, the test is mirroring the
> implementation and it does not ship.

Two further project conventions bear on it. The **AST-scan pattern** already in the suite
(`test_advisory_lock_ids.py`, `test_i18n_completeness.py`) is the accepted house style for
cross-tree *invariants* — it is not "string matching" and it does not fall under this rule.
And phase 10's own rule is the standard for anything else: **"a rule that must first be made
true cannot be enforced before it is true"** — which is why the two AST architecture rules it
routed here are refused rather than built (§6).

### 1.6 Task shape

Every block's implementor task follows `.ai\tasks\templates\task_template.yaml`: semantic
`targets` with `type`/`name`, `semantic_anchors`, `changes`, `acceptance_criteria`,
`source_reference` / `source_section`. **Line numbers are never used as task targets.** If a
test file is edited, the target is the test function or test class by name, and the fixture
or module by fixture or module name.

---

## 2. Scope decisions table (acceptance contract for execution)

`reconciliation` = produces a record or a schedule, no behaviour change, no test added.
`configuration` = CI / pytest / settings configuration; no production code; changes what the
suite *measures* or *tolerates*. `coverage` = adds or rewrites a test; subject to §1.5.

| ID | Class | Disposition | Block | Severity | One-line reason |
|---|---|---|---|---|---|
| `11-TEST-001` | **reconciliation + coverage** | **implement as two sub-commits — gated on Q1 (ownership) **and** Q2 (AD-008 branch).** (a) explicit `status=` at the **62 defaulted** sites, behaviour-preserving; (b) flip both factory defaults to `PUBLISHED`, correct `.kilo/rules/commands.md` and `docs/99-agent/rules.md`, add a self-verifying regression guard. **The 62-site pass does not start until AD-008 is decided** | **14** | HIGH | The defect is real — the fixture fabricates a state no production writer commits — but the scope is **124 sites in 22 files**, not 111 in 19 (C-1), and under the "make `ON_MODERATION` durable" branch the migration **evaporates**. Seven plans forbid the file and one claims it (C-10) |
| `11-TEST-002` | **configuration** | **implement — gated on Q2 (measure first).** Both workflows (C-3). Explicit `--cov-config=pyproject.toml --cov=src/backend --cov=src/telegram_bot --cov-branch` is the **preferred** shape over the positional `working-directory: .`, because it is immune to the next `working-directory` change | **2** | HIGH | `[tool.coverage.*]` is read from the CWD only and the pytest step's CWD is `src/backend`, so `branch`, `source`, `omit` and **`fail_under = 80` are all inert**. `ci-nightly.yml` has the identical defect and the report never mentions it. **The edit is one line; the effect is a gate that has never fired beginning to fire** |
| `11-TEST-003` | **configuration + coverage** | **implement as two sub-blocks.** Step 1 = the test-side bound in `config/settings/test.py` — **gated on Q3 and hard-blocked on phase 03's `DB-002` and `DB-004`**. Step 2 = the hostile-`?features=` test — **gated on Q6** (whose commit it lands in, and which file). Neither the production cap nor the `feature_slugs` bound is re-filed | **5**, **6** | HIGH | The suite cannot host a runaway-query test today: `config/settings/test.py` sets no `OPTIONS` on `DATABASES["default"]`, and a repo-wide search for `statement_timeout\|lock_timeout\|idle_in_transaction_session_timeout` across `src/` and `docker/` returns **0 hits**. The largest `?features=` list anywhere in the suite is **2** |
| `11-TEST-004` | **coverage** | **implement — the rollback-negative half and the alert-path `transaction=True` half, folded into BLOCK 7.** `test_advisory_lock_release_log.py` is **phase 03 BLOCK 2's** ("it must rewrite the two tests") and is **not** touched here | **7** | HIGH | Two of the four production `on_commit` sites — including the one that sends a real Telegram message — are patched out in their only tests, and no rollback-negative test exists anywhere in `src/`. The failure it would miss is user-visible and irreversible |
| `11-TEST-005` | **coverage** | **implement the corrected narrow scope only.** Behavioural cross-process assertions for the 2–3 highest-value rows, plus a **predicate-equality** test (the AUT-002 / PII-104 shape). Its proposal 3 — do **not** run the real bot process inside pytest — is **endorsed** and restated as a binding constraint | **12** | MEDIUM | The report's two headline claims are refuted: at least five real cross-tree tests exist, and `test_edit_views_locking.py` already exercises two independent transactions per thread under `transaction=True`. What survives is a bounded, additive ~6-test set following an existing pattern — **not** a new harness |
| `11-TEST-006` | **coverage** | **implement — lands in the same commit as phase 08's NUL production fix.** Extend `TestSearchViewInputRobustness` with a parametrised C0 case (`%00`, `%01`, `%0a`, `%1b`) asserting HTTP 200 and zero results | **9** | MEDIUM | U+200B is format-class, not C0; no `\x00` and no C0 character reaches any `?q=` test. The two NUL tests the report claimed did not exist **do** exist — on the **media** path. The project knows about NUL hostility in one subsystem and has not carried the discipline into search |
| `11-TEST-007` | **coverage** | **implement items 2 and 3 only** — the `Meta.constraints` introspection test and the `transaction=True` two-thread dedup test. **Item 1 (the `UniqueConstraint` + migration) is phase 08's** and must not be actioned twice | **10** | MEDIUM | `PopularSearch.query_normalized` is `CharField(max_length=200, db_index=True)` with **no `unique=True`**, `Meta` carries only `db_table`, and the dedup is a plain `get_or_create` under READ COMMITTED. The three existing dedup tests are sequential and single-threaded — they cannot interleave. **The introspection test cannot pass until phase 08's migration lands** |
| `11-TEST-008` | **configuration** | **implement — gated on Q5.** Record the seed by uploading `.pytest_cache` as a CI artifact next to `coverage.xml`; pin `--randomly-seed` only if Q5 says so | **4** | MEDIUM | `pytest-randomly 5.0.0` is auto-enabled, no seed is passed anywhere, and `-q` suppresses `pytest_report_header`, which is the only place the seed is reported. **Correction:** `.pytest_cache/v/cache/randomly_seed` is **absent** in this tree (C-6), so local replay does not work today either — the finding is *narrower* than the report's mitigation claimed and *stronger* than its headline |
| `11-TEST-009` | **configuration** | **implement — gated on Q4.** A `timeout` / `timeout_method` pair in `[tool.pytest.ini_options]` and `timeout-minutes` on the `test` **and** nightly jobs | **3** | MEDIUM | `pytest-timeout 2.4.0` and `pytest-rerunfailures 16.6.1` are installed and configured **nowhere**. `timeout-minutes` appears **0 times** in `ci.yml` — so a hung test in CI is bounded only by GitHub's default 6-hour job limit, and cancelled with no diagnostic |
| `11-TEST-010` | **coverage + reconciliation** | **implement a written rule, not a blanket deletion — gated on Q8.** Keep the cross-tree invariants and the shipped regression guards; convert or delete only the assertions that mirror an implementation | **11** | MEDIUM | 27 sites in 8 files, reproduced exactly (two paths corrected, C-5). `test_admin_pii_containment.py` is the extreme case — 4 assertions, the whole module, and the **only** admin-surface audit in the suite, and it cannot see AUT-005 / PII-103 because that defect is expressed as an **absence**. Deleting all 27 would delete `test_migrate_locked.py::TestSessionLockLogging`, a shipped phase-01 hard guard |
| `11-TEST-011` | **coverage** | **implement — gated on Q9.** Assert the **effect** of the four real data migrations (`ads/0003_dedup_per_user_drafts`, `search/0002_redact_search_queries`, `core/0003_add_bot_username`, `core/0002_seed_default`) through the existing **subprocess** shape | **13** | MEDIUM | `DisableMigrations` makes the test schema a `syncdb` of current models, and `_restore_test_schema_post_db_setup` compensates for reference data only. `test_migrations.py` asserts applicability and idempotency, never effect. `ads/0003`'s effect is the **precondition** for `ads/0004`'s UNIQUE constraint; `search/0002`'s is a PII rewrite. **Correction:** there is no squash *migration*; the command exists and is already tested (C-7) |
| `11-TEST-012` | **coverage** | **implement as an extension of `apps/core/tests/test_support_admin.py` — gated on Q7.** `get_form(request)` field names **and widget classes** for every registered `ModelAdmin`; `get_actions(request)` for every admin declaring `actions`. One rendered-page smoke test, lowest value, optional under Q7 | **8** | MEDIUM | The premise is **refuted** — that file already carries 12 registered-`ModelAdmin` introspection tests — so the remedy is an extension, not a new module, and the cost is lower than reported. `get_form(` and `get_actions(` return **0 hits across all of `src/`**, and no test issues `Client().get("/admin/…")`. Phase 06's **VAL-007 is mandatory**: `test_support_admin.py` already asserts on `SupportContactAdmin.telegram_id`, so a blanket data-subject rule false-positives on a support *channel* id |
| `11-TEST-013` | **reconciliation** | **record CLOSED.** No remediation. Its item 2 (add a `basedpyright .` step for `src/telegram_bot`, move `ruff` to the repo root) survives **only if** phase 01's `lint`/`typecheck` block has not already done it — **Q12** | **1** (records), **16** (CI scope) | **LOW → closed** | `basedpyright .` returns **0 errors, exit 0** in both scopes and `ruff check src/` is clean (C-2). The report's 12+2 errors were true at `9e96b84` and are false now, with no one editing the tests. **The root cause is phase 01 `ENT-004`'s; re-filing it would ship the same fix twice** |
| `11-TEST-014` | **coverage** | **implement the `transaction=True` scaffold — two tests, both in a `transaction=True` scope.** Shared-key-not-freed and last-reference-freed. **Lands with or before phase 07's `MEDIA-001`.** The `advisory_lock` release-log site is phase 03's | **7** | MEDIUM | 0 `TestCase`, 0 `TransactionTestCase`, 0 `captureOnCommitCallbacks`; **48** `transaction=True` scopes in **39** files. Two of four production `on_commit` sites are **structurally unobservable**. **The media surface is 2 files / 7 tests, not a sweep surface** (C-4) — so a refcount bug inside the callback would be verified by 7 tests, and its failure mode is asymmetric and irreversible |
| `11-VAL-001` | **reconciliation** | **record only.** Correct the phase-report anchor to `6413df5`; re-measure every count that carries remediation weight | **1** | MEDIUM | `0c91666` is unresolvable and **fourteen** further citations have drifted since `9e96b84` — including three of the report's own re-measured numbers (C-8). The report's *narrative* is reliable; its *line citations* are indicative only |
| `11-VAL-002` | **reconciliation** | **record only.** No source change | **1** | MEDIUM | The scoping premise *"tests using bare `TestCase` are structurally blind to `on_commit`"* is **factually inapplicable**: zero `TestCase` subclasses exist. The exposure is real and arrives through `pytest.mark.django_db`. This item exists so the exposure is not double-counted between `11-TEST-004` and `11-TEST-014`, and so no block is scoped against the wrong mechanism |
| **`Q1`** | — | **GATED** — coordinator | **14** | — | **BLOCKER.** Seven plans forbid `src/backend/conftest.py`, one claims it, this plan needs it |
| **`Q2`** | — | **GATED** — phase 05 owner + coordinator | **14** | — | Decides whether the 62-site pass is work or no-op |
| **`Q3`** | — | **GATED** — Planner, with phase 03 | **5** | — | Mechanism and value of the test-side bound; hard-blocked on `DB-002` |
| **`Q4`** / **`Q5`** | — | **GATED** — Planner | **3**, **4** | — | Timeout shape/value, and pin-vs-record |
| **`Q6`** | — | **GATED** — Planner + coordinator | **6** | — | Whose commit carries the hostile-`?features=` test |
| **`Q7`** / **`Q8`** | — | **GATED** — Planner (+ phase 06 / Researcher) | **8**, **11** | — | Admin-contract scope and assertion kind; the `getsource` rule |
| **`Q9`** / **`Q10`** / **`Q11`** | — | **GATED** — Planner / Researcher | **13**, **15** | — | Migration-effect shape; zero-coverage disposition; the phase-10-routed AST rules |
| **`Q12`** | — | **GATED, narrow** — Auditor, from the commit log | **1**, **16** | — | What actually fixed the typecheck gate |

**Block classification summary:** `reconciliation` = **1, 11, 15** ·
`configuration` = **2, 3, 4, 5, 16** · `coverage` = **6, 7, 8, 9, 10, 12, 13, 14**.

---

## 3. Execution blocks

Sixteen blocks. **One Implementor, strictly sequential, one commit per block** (§1.4). The
numbering *is* the serial order, and the order is chosen so that **each contended test file
is written by exactly one phase-11 block per run**, configuration before coverage, and
everything that other phases gate on before the thing that gates them.

```
BLOCK 1  reconciliation + schedule   ──▶ the deliverable; nothing else starts without it
BLOCK 2  CI coverage config          ──┐
BLOCK 3  hang bounds                 ──┤
BLOCK 4  seed determinism            ──┤  configuration: independent of each other,
BLOCK 5  test statement_timeout      ──┘  run first, pay for everything below
BLOCK 6  ?features= bound test   <── external gate: phase 08 BLOCK 1 (SRCH-001)
BLOCK 7  on_commit scaffold      <── external gate: phase 07 MEDIA-001
BLOCK 8  admin form contract     <── external gate: phase 06 VAL-007
BLOCK 9  ?q= hostile corpus      <── external gate: phase 08 BLOCK 3 (NUL fix)
BLOCK 10 dedup concurrency       <── external gate: phase 08 BLOCK 5 (UniqueConstraint)
BLOCK 11 getsource rule          ──▶ 8 (the rule names what 8 replaces)
BLOCK 12 cross-process equality  <── external gate: phase 04 / phase 06 predicates
BLOCK 13 migration-effect tests  <── external gate: phase 02 BLOCKs 3/4/5/9
BLOCK 14 create_test_ad contract <── Q1 + Q2 BLOCKERS, coordinator
BLOCK 15 zero-coverage triage    ──▶ 8 (cabinet hub), independent of 14
BLOCK 16 handbook + CI scope     ──▶ 2 (the handbook's claim is false until 2 lands)
```

Eleven blocks carry a labelled **decision required before implementation** gate or an
external phase gate. **A gated block does not start until the answer is written down; the
Implementor is forbidden from choosing the option** (§1.4, §8.1).

---

### BLOCK 1 — Reconciliation, ownership gate, and the ordered test-change schedule

| | |
|---|---|
| **Findings owned** | `11-VAL-001`, `11-VAL-002`, `11-TEST-013` (closed), `11-TEST-001`'s count correction, and **this plan's deliverable** |
| **Class** | **reconciliation** — no production change, no test added, no configuration change |
| **Depends on** | nothing in-plan |
| **Blocks** | **every other block in this plan**, and — through the schedule — phases 03, 05, 06, 07, 08, 09 and 10 |
| **Priority** | **P0.** This is the block whose output the other plans are checked against |
| **Risk level** | **LOW** execution risk; **HIGH** value. The risk is *not doing it* |
| **Required agents** | **Auditor · Planner · Validator.** Researcher required for the ownership-map read of the seven other plans. **No Implementor edits code** — the Implementor's only action is the commit |

**This block's deliverable is a schedule, not a fix.** Four test files are claimed by more
than one phase and one file — `src/backend/conftest.py` — is claimed by exactly one phase
and forbidden by seven. Until those are reconciled, every other block's ordering is a guess.

#### 3.1.1 What the Auditor must produce, and where it goes

The output is written into this block's task `extra_context` **and** committed to the
tracker entry under `11-VAL-001`. It has five parts:

**(a) The re-measured census.** Re-run the static measurements at the execution anchor —
`test_*.py` count, test-function count, `Test*` class count, fixture count across conftests,
`transaction=True` scope count and file count, `inspect.getsource` count and per-file
distribution, `TestCase` / `TransactionTestCase` / `captureOnCommitCallbacks` counts, and the
`create_test_ad` explicit/defaulted/total split with its per-file table. **The numbers in
§0.2.2 and §0.2.3 are the baseline; the number that ships is the re-measured one**, and
§7 records that the `ON_MODERATION` count moved 111 → 124 and the typecheck errors 12+2 → 0
between two anchors with nobody editing the tests.

**(b) The four contested test files, with the owning phase and the ordering rule for each.**

| Contested test file | Claiming phases | Phase-11's block | Ordering rule |
|---|---|---|---|
| `src/backend/conftest.py` | **05** BLOCK 4 claims · 03 "must not edit it at all" · 06, 07, 08, 09, 10 "**nobody**" · 04 forbids fixture reshaping | **14** | **GATED on Q1.** Seven plans forbid it, one claims it, this plan needs it. **BLOCKER** |
| `src/backend/apps/search/tests/test_search_view.py` | **08** BLOCKs 1, 3, 4, 5, 6, 7, 9, 10, 11, 12 · **10** BLOCK 14 · plus `11-TEST-006` | **9** | **Serialise:** phase 08 BLOCK 3 (the NUL fix) → phase 10 BLOCK 14 (the context builder) → phase 11 BLOCK 9. **A block that must re-read** re-reads the file and phase 08's and phase 10's plans **immediately before editing** |
| `src/backend/apps/search/tests/test_search_query_count.py` + `test_search_slo.py` | **08** BLOCKs 1, 3, 11 · **10** BLOCKs 14, 15 | **none** | **Phase 11 does not edit either.** They are the tripwires that detect whether BLOCKs 5 and 6 changed anything. `test_search_slo.py` is the **only wall-clock gate** in the suite and CI runs it as a separately named step |
| `src/backend/apps/core/tests/test_advisory_lock_ids.py` | **01, 03, 05, 06, 07, 10** — six phases | **none** | **Phase 11 allocates no `AdvisoryLockId` and does not edit this file.** It is a six-way three-file-one-commit unit for whichever phase *does* allocate |
| `src/backend/apps/core/tests/test_ad_image_delete_signal.py` (+ `test_delete_photo_single_call.py`) | **03** BLOCK 1 · **05** BLOCK 13 · **07** BLOCKs 1, 2, 11 | **7** | **Phase 11 BLOCK 7's scaffold lands BEFORE or WITH phase 07's `MEDIA-001`,** which is exactly where phase 07 VAL-003 already found the three tests that will break. `test_advisory_lock_release_log.py` is **phase 03 BLOCK 2's** and is not touched |

Plus the remaining sixteen multi-claim files from the code context §8.2, each with one
sentence: *owning phase, ordering rule, or "phase 11 is read-only"*.

**(c) The ownership ruling for `src/backend/conftest.py`** — Q1's three options and the
coordinator's answer, recorded verbatim with the date and the reasoning. **BLOCK 14 does not
start without this line.**

**(d) `11-TEST-013`'s closure record with Q12's answer.** Which commit made `basedpyright`
green in both scopes. If it was the untyped `advisory_lock` context manager, note that the
fix landed in **production** and the tests followed; if it was anything else, name it and
flag the phase that may reintroduce it. **`11-TEST-013` is recorded closed only after this
line exists.**

**(e) The three facts the report does not mention and this plan carries forward:** the
`ci-nightly.yml` twin of the `--cov` defect; the 2-file / 7-test media `transaction=True`
surface; and the absence of `.pytest_cache/v/cache/randomly_seed`.

**Binding constraints**

1. **No production code, no test, no settings file, no workflow file is edited by this
   block.** It produces a record.
2. **No other plan file and no `.ai/audit/**` file may be edited** to record the answer.
   `git status --short .ai` must show no new modifications beyond the pre-existing deletions
   and this plan's own file.
3. **The re-measured number ships, not the §0.2.3 number.** Where they differ, the commit
   body states both and names the anchor.
4. **`11-VAL-002` prevents double-counting**: the `on_commit` exposure is counted **once**,
   in `11-TEST-014`, not in both `11-TEST-004` and `11-TEST-014`.
5. **No block may start on the strength of the report's line citations.** VAL-001 confirmed
   fourteen of them drifted; treat narrative as reliable, citations as indicative.

**Implementor task**

```yaml
id: task_11_b01_reconciliation_and_schedule
title: "Produce the phase-11 reconciliation record and the ordered test-change schedule"
priority: high
depends_on: []
source_reference: ".ai/plans/11-test-coverage-remediation.md"
source_section: "BLOCK 1 - Reconciliation, ownership gate, and the ordered test-change schedule"
source_blocks: ["BLOCK 1"]
description: >
  Re-measure the phase-11 census at the execution anchor, resolve who owns
  src/backend/conftest.py, record why the basedpyright gate is green, and publish the ordered
  test-change schedule that every other phase's plan is checked against. Four test files are
  claimed by more than one phase; this block turns each claim into a single owner plus an
  ordering rule. No code, no test, no settings and no workflow file is edited.
goals:
  - "re-measure and publish the static census at the execution anchor"
  - "obtain and record a written answer to Q1 (conftest.py ownership) and Q12 (what fixed the typecheck gate)"
  - "publish one owner plus one ordering rule for every contested test file"
  - "record 11-TEST-013 as closed only after Q12 is answered"
  - "edit no code, no test, no settings, no workflow, no plan, no audit file"
files:
  - path: ".ai/audit/99-validation/11-test-coverage-validated-findings.md"
    targets:
      - type: module
        name: "11-test-coverage-validated-findings"
    semantic_anchors: {}
changes: []
acceptance_criteria:
  - "the re-measured census is recorded with its anchor commit and the commit body states both the old and the new number wherever they differ"
  - "Q1 has a written answer naming the option, the decider and the date; BLOCK 14 may not start without it"
  - "Q12 has a written answer naming the commit that made basedpyright green"
  - "every contested test file in the schedule has exactly one owning phase and one ordering rule"
  - "git status --short .ai shows no new modifications beyond the pre-existing .ai/audit deletions and .ai/plans/11-test-coverage-remediation.md"
```

---

### BLOCK 2 — Make CI actually load the coverage configuration (`11-TEST-002`)

| | |
|---|---|
| **Findings owned** | `11-TEST-002` (HIGH) |
| **Class** | **configuration** — no production change, no test added |
| **Depends on** | BLOCK 1 (the schedule) |
| **Blocks** | BLOCK 16 (the handbook's "80 % branch coverage gate" claim is false until this lands) |
| **Priority** | P1 — the highest-value-per-line change in the report, and the one whose *effect* is not yet known |
| **Risk level** | **HIGH** — not because the edit is hard, but because it turns on a gate that has never fired |
| **Required agents** | **Auditor · Planner · Validator.** Researcher required if the coverage number requires interpreting which packages dragged it down |

**Decision required before implementation — Q2: does the real number clear 80 %?**

`coverage.py` resolves its configuration from the **current working directory only**; it does
not walk upward. Measured at the report's anchor: from `src/backend`,
`config_file=None, branch=False, source=None, fail_under=0.0, omit=0`; from the repo root,
`config_file=<root pyproject.toml>, branch=True, source=['src/backend','src/telegram_bot'],
fail_under=80.0, omit=7`. The CI pytest step runs with `working-directory: src/backend` and
a **bare `--cov`**. So `branch`, `source`, `omit` **and** `fail_under = 80` are all inert,
`coverage.xml` is uploaded to a `coverage-report` artifact with a 30-day retention and
**nothing consumes it**, and coverage could fall to 30 % with CI green.

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | **Explicit flags** on both workflows: `--cov-config=pyproject.toml --cov=src/backend --cov=src/telegram_bot --cov-branch` | **Gains:** immune to the next `working-directory` edit, self-documenting, and it makes the *scope* of the gate explicit in the workflow rather than implied by the CWD. **Costs:** longer command line, and the flags must be kept in step with `[tool.coverage.run] source` if that list ever changes. The report's own advisory prefers this over its primary recommendation |
| **(b)** | **Positional fix**: set `working-directory: .` on the pytest step of both workflows | **Gains:** one line each; the config then loads because the CWD becomes the repo root. **Costs:** the gate becomes *positional* — the next agent who changes `working-directory` silently disables coverage again, which is the exact failure this finding is about. Does not make the scope self-documenting |
| **(c)** | **(a) plus** an explicit `--cov-fail-under` | **Gains:** the threshold is visible in the workflow. **Costs:** duplicates `fail_under` from `pyproject.toml`, creating two places to drift. **Do not do this** unless Q2 shows the two values disagree |

**The second half of Q2 is not a choice at all: is 80 % actually met?** Neither the report
nor the code context ran a coverage measurement — both are static (§0.2.4 item 3). If the
real number is below 80, this block **cannot land as option (a) or (b)** without either a
`fail_under` that is honest about the current state or an explicit decision to land a
failing CI step and fix coverage afterwards. **Both are defensible; neither may be chosen by
the Implementor.**

**Binding constraints**

1. **Both workflows, or neither.** `.github/workflows/ci-nightly.yml` carries the identical
   bare `--cov` with `working-directory: src/backend` (C-3). Phase 11 is the **first** phase
   to touch that file. Fixing `ci.yml` alone leaves the nightly measuring the same inert
   configuration — a half-fix that looks complete.
2. **Pytest resolution is unaffected and must stay that way.** `rootdir` discovery *does* walk
   upward, so `testpaths = ["src/backend", "src/telegram_bot"]` and
   `pythonpath = ["src", "src/backend"]` both resolve from the current CWD. **The bot tree is
   already collected and already measured** — the report's claim that it is absent from the
   report is **refuted**. What is wrong is that it is measured with `branch=False` and with
   `omit` ignored. **Do not "fix" a non-problem by changing `testpaths`.**
3. **`--cov-config` or `working-directory`, not both.** Option (b) alone is acceptable; (a)
   and (b) together are redundant and would make the next reader unsure which mechanism is
   load-bearing.
4. **The commit must not claim a coverage improvement.** This block changes *what is
   measured*, not *how much is covered*. If the number moves, it moves because branch
   coverage is now counted.
5. **Verification is a log assertion, not a percentage assertion**: after the change the CI
   log must contain `Required test coverage of 80.0% reached` (or the exact failure text
   under Q2's second half), **and** the term report must show `Branch` / `BrPart` columns.
6. **No other step in either workflow may be touched.** Phase 01 owns the `lint`/`typecheck`
   jobs; phase 09 BLOCK 15 holds part of `ci.yml`.

**Implementor task**

```yaml
id: task_11_b02_ci_coverage_config
title: "Make CI load the coverage configuration in both workflows (11-TEST-002)"
priority: high
depends_on: [task_11_b01_reconciliation_and_schedule]
source_reference: ".ai/plans/11-test-coverage-remediation.md"
source_section: "BLOCK 2 - Make CI actually load the coverage configuration"
source_blocks: ["BLOCK 2"]
description: >
  The pytest step in .github/workflows/ci.yml runs with working-directory: src/backend and a
  bare --cov. coverage.py resolves its configuration from the current working directory only,
  so [tool.coverage.run] branch/source/omit and [tool.coverage.report] fail_under = 80 are all
  inert and nothing consumes coverage.xml. .github/workflows/ci-nightly.yml has the identical
  defect and is not mentioned by the report. Fix both, under the Q2 option, after the real
  coverage number has been established.
goals:
  - "make both workflows load the repository's [tool.coverage.*] configuration"
  - "establish the real branch-coverage number before the gate is enabled"
  - "change no production code, no test and no other workflow step"
files:
  - path: ".github/workflows/ci.yml"
    targets:
      - type: job
        name: test
    semantic_anchors:
      run_value_contains: "--cov"
  - path: ".github/workflows/ci-nightly.yml"
    targets:
      - type: job
        name: seed
    semantic_anchors:
      run_value_contains: "--cov"
changes:
  - action: modify_config
    description: >
      Apply the Q2 option to the pytest step of both workflows. Do not touch any other step,
      any other job, or the artifact upload's retention.
acceptance_criteria:
  - "the CI log contains 'Required test coverage of 80.0% reached' (or the Q2-recorded failure text)"
  - "the term report shows Branch and BrPart columns"
  - "src/telegram_bot appears in the measured source set"
  - "testpaths is unchanged and both trees are still collected"
  - "the commit body names the Q2 option, the measured number, and the anchor"
```

---

### BLOCK 3 — Give the suite a hang bound (`11-TEST-009`)

| | |
|---|---|
| **Findings owned** | `11-TEST-009` (MEDIUM) |
| **Class** | **configuration** |
| **Depends on** | nothing in-plan (BLOCK 1's schedule names the file owners) |
| **Blocks** | BLOCKS 5 and 6 — a test that deliberately provokes a slow query needs to know what the harness does when it is slow |
| **Priority** | P1 — **this block pays for every other block in the plan.** Nothing catches a hang, and the shared test database is what a hang takes down |
| **Risk level** | **MEDIUM** — a global `timeout` interacts with the suite's only wall-clock gate and with one deliberate `time.sleep` |
| **Required agents** | **Auditor · Planner · Validator.** Researcher not required |

**Decision required before implementation — Q4: what shape, what value, what method?**

`pytest-timeout 2.4.0` is installed. `[tool.pytest.ini_options]` has **no `timeout` key and
no `timeout_method`**. `--timeout` and `--reruns` appear in **zero** lines of `ci.yml`,
`ci-nightly.yml`, `docker/entrypoint-test.sh` and `Makefile.ps1`. A search for
`timeout-minutes` in `ci.yml` returns **0 matches** — the report already corrected itself
here, and the correction is correct: **no job in the repository has a wall-clock bound.** A
hung test in CI is bounded by GitHub's default 6-hour job limit and is cancelled with no
diagnostic.

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | One global `timeout` in `addopts`/`ini_options`, `timeout_method = "signal"` | **Gains:** bounds *every* test, and a signal actually interrupts a blocking PostgreSQL query. **Costs:** one value must be larger than the slowest legitimate test. `TestSearchResponseSLORegression` asserts a real `/search/` request at ≥50 published ads completes within `SEARCH_SLO_MS == 2000`, and `apps/lookups/tests/test_lookup_cache_swr.py` sleeps `0.2` deliberately across 27 tests in 7 classes |
| **(b)** | Global `timeout` as a large backstop **plus** a per-marker value for `slow` | **Gains:** the backstop cannot red a legitimate slow test and the marker is where a slow test belongs. **Costs:** two values to maintain, and the marker vocabulary already has 8 entries — **no new marker is added by this plan** |
| **(c)** | `timeout_method = "thread"` | **Gains:** portable across platforms without signals. **Costs: it does not stop the query.** It returns while the runaway PostgreSQL statement keeps running — which is precisely the failure mode `11-TEST-003` is about. **A thread-method timeout would defeat the block's own purpose** |
| **(d)** | `timeout-minutes` on the `test` and seed jobs only, no `timeout` key | **Gains:** turns a 6-hour hang into a diagnosable job cancellation. **Costs:** no diagnostic *within* the job — the suite still hangs for the full ceiling |

**The Implementor may not choose.** (c) is listed so the trade-off is explicit; it is the one
option that looks safe and is not.

**Binding constraints**

1. **Both workflows.** `ci-nightly.yml` runs the `seed` marker, whose bulk cases are the
   slowest thing in the repository. A ceiling tuned for the fast gate will red the nightly.
2. **The value must clear the fastest-failing legitimate test.** Before choosing, the
   Implementor runs `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="-k TestSearchResponseSLORegression --reuse-db --durations=20" test`
   and records the slowest observed case. **A ceiling chosen from imagination is a red gate
   on arrival.**
3. **`--reruns` is out of scope.** `pytest-rerunfailures` is installed and unconfigured, but
   re-running a failed test in a suite where `TRUNCATE … CASCADE` races across xdist workers
   can mask a real teardown failure. It is de-scoped (§6).
4. **No new marker, no `conftest.py` fixture.** The bound belongs in configuration; a fixture
   would be a session-scoped fixture in the most contended file in the repository.
5. **No other `ci.yml` step may be touched** (phase 01 owns `lint`/`typecheck`; phase 09
   BLOCK 15 holds part of `ci.yml`).

**Implementor task**

```yaml
id: task_11_b03_hang_bounds
title: "Bound a hung test in pytest configuration and in both CI jobs (11-TEST-009)"
priority: high
depends_on: [task_11_b01_reconciliation_and_schedule]
source_reference: ".ai/plans/11-test-coverage-remediation.md"
source_section: "BLOCK 3 - Give the suite a hang bound"
source_blocks: ["BLOCK 3"]
description: >
  pytest-timeout 2.4.0 and pytest-rerunfailures 16.6.1 are installed and configured nowhere.
  [tool.pytest.ini_options] has no timeout key; --timeout and --reruns appear in zero lines of
  ci.yml, ci-nightly.yml, docker/entrypoint-test.sh and Makefile.ps1; and timeout-minutes
  appears 0 times in ci.yml, so no CI job in the repository has a wall-clock bound. Add the
  pytest bound under the Q4 option and a job ceiling to both workflows, with the value chosen
  from an observed slowest case rather than from imagination.
goals:
  - "bound a hanging test from inside the suite"
  - "bound a hanging CI job in both workflows"
  - "add no marker, no fixture, no dependency and no --reruns"
files:
  - path: "pyproject.toml"
    targets:
      - type: config_table
        name: "tool.pytest.ini_options"
  - path: ".github/workflows/ci.yml"
    targets:
      - type: job
        name: test
  - path: ".github/workflows/ci-nightly.yml"
    targets:
      - type: job
        name: seed
changes:
  - action: modify_config
    description: >
      Add the Q4 timeout/timeout_method pair and the two job ceilings. Do not add --reruns.
acceptance_criteria:
  - "a deliberately hanging test is killed rather than hanging the job, and the failure names the test"
  - "the fastest gate and TestSearchResponseSLORegression are green unchanged with the chosen value"
  - "both ci.yml and ci-nightly.yml carry a timeout-minutes value"
  - "no marker was added and no conftest.py fixture was introduced"
  - "the commit body names the Q4 option, the observed slowest case and the chosen value"
```

---

### BLOCK 4 — Make the random seed recoverable (`11-TEST-008`)

| | |
|---|---|
| **Findings owned** | `11-TEST-008` (MEDIUM) |
| **Class** | **configuration** |
| **Depends on** | nothing in-plan |
| **Blocks** | nothing. But BLOCK 3's value choice is *harder* to justify without it — a shuffled suite with a recoverable seed is debuggable; a hung test in an unreproducible order is not |
| **Priority** | P2 |
| **Risk level** | **LOW** execution / **MEDIUM** value — option (a) has a real downside the report does not mention |
| **Required agents** | **Auditor · Planner.** No separate Validator; the fast gate must be green |

**Decision required before implementation — Q5: pin the seed, or record it?**

`pytest-randomly 5.0.0` is installed and auto-enabled. `addopts` carries no
`--randomly-seed` and no disable; `ci.yml`, `ci-nightly.yml`, `docker/entrypoint-test.sh`
and `Makefile.ps1` all pass no seed. The seed is reported **only** through
`pytest_report_header`, which `-q` (verbosity −1) suppresses. CI archives only
`coverage.xml`, never `.pytest_cache`.

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Pin `--randomly-seed` in `addopts` | **Gains:** fully deterministic, locally and in CI; the finding's primary recommendation. **Costs: it removes the plugin's reason for existing.** `pytest-randomly` is installed precisely to find order-dependence bugs on every run; a pinned seed turns that off permanently, and an order-dependent test that a shuffle found would now only be found when someone changes the pin |
| **(b)** | Upload `.pytest_cache` as a CI artifact next to `coverage.xml` | **Gains:** keeps the shuffle — which is the *finding* being detected — while recording the seed deterministically, one artifact line, `-q` untouched. **Costs:** the seed is only reachable after a failed run; local and CI replay differ unless the local cache exists |
| **(c)** | Both | **Gains:** CI is deterministic and the local shuffle still hunts. **Costs: (a)'s downside is only half-mitigated** — a pinned seed still means CI never exercises a different order |

**Correction the Implementor must know (C-6):** the report's mitigating claim — that the seed
is read back from `.pytest_cache/v/cache/randomly_seed`, so local reproduction already
works — is **true of the plugin and false of this checkout**. The file is absent;
`.pytest_cache/v/cache/` holds only `lastfailed` and `nodeids`. Local seed replay does not
work today. That makes the finding *narrower* than the report claimed and *stronger* than
its headline.

**Binding constraints**

1. **Do not change `-q`.** Raising verbosity to surface the seed header changes output
   formatting across every CI log and every developer's terminal, for a problem a `.po`-
   free artifact upload solves.
2. **The artifact must be uploaded from the pytest step's own working directory.** The
   `pytest-randomly` cache path is relative to `rootdir`, and `rootdir` is the repo root.
3. **No `conftest.py` fixture may print or log the seed** — the most contended file in the
   repository is claimed by one phase and forbidden by seven (Q1), and this is not the block
   to change that.
4. **The nightly is included.** Both workflows must record the seed or neither does.
5. **The commit must state which option was taken and why**, because option (a) *reduces*
   detection power and that trade-off must be visible to the next reader.

**Implementor task**

```yaml
id: task_11_b04_seed_recoverable
title: "Make the pytest-randomly seed recoverable (11-TEST-008)"
priority: medium
depends_on: [task_11_b01_reconciliation_and_schedule]
source_reference: ".ai/plans/11-test-coverage-remediation.md"
source_section: "BLOCK 4 - Make the random seed recoverable"
source_blocks: ["BLOCK 4"]
description: >
  pytest-randomly 5.0.0 is auto-enabled, no seed is passed in addopts or in any of ci.yml,
  ci-nightly.yml, docker/entrypoint-test.sh or Makefile.ps1, and -q suppresses the
  pytest_report_header line that is the only place the seed is reported. Apply the Q5 option
  so a failed CI run can be reproduced locally, without reducing the shuffle's detection
  power by default.
goals:
  - "make the seed of a failed CI run recoverable"
  - "change no verbosity setting and add no conftest fixture"
files:
  - path: ".github/workflows/ci.yml"
    targets:
      - type: job
        name: test
  - path: ".github/workflows/ci-nightly.yml"
    targets:
      - type: job
        name: seed
  - path: "pyproject.toml"
    targets:
      - type: config_table
        name: "tool.pytest.ini_options"
changes:
  - action: modify_config
    description: >
      Apply the Q5 option to both workflows and, under option (a) or (c), to addopts.
acceptance_criteria:
  - "a failed CI run's seed is recoverable from an artifact or from addopts, per the Q5 option"
  - "-q is unchanged in every invocation"
  - "no file under src/backend/conftest.py or src/telegram_bot/tests/conftest.py was modified"
  - "the commit body names the Q5 option and states explicitly whether shuffle detection was reduced"
```

---

### BLOCK 5 — Bound the test database so a runaway query cannot take it down (`11-TEST-003`, step 1)

| | |
|---|---|
| **Findings owned** | `11-TEST-003` (HIGH), step 1 only |
| **Class** | **configuration** — a test-settings option, **not** production code and **not** a schema change |
| **Depends on** | BLOCK 3 (the harness's own timeout must be understood before a second bound is added) |
| **Blocks** | BLOCK 6 (the hostile-`?features=` test cannot be written before the bound exists) |
| **External gate** | **phase 03 `DB-002` must have landed** · phase 03 `DB-004` sizes the value |
| **Priority** | P1 |
| **Risk level** | **HIGH** — this is a global change to all 2 403 test functions, and phase 03 recorded a live hazard |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four** |

**The live hazard, stated once.** Phase 03 recorded that `statement_timeout` produces an
`OperationalError` on exactly the kind of INSERT `record_event` issues, and that
`record_event` currently swallows it. **Landing a statement-level bound before `DB-002`
converts a swallowed error into a new failure mode in the analytics path.** That is why this
block is HARD-blocked on `DB-002` and not merely sequenced after it.

**What is confirmed.** `ListingsQueryParams.feature_slugs` is
`Field(default_factory=list)` with no `max_length` and no validator; the join loop is one
JOIN per slug with no cap; both entry points pass `request.GET.getlist("features")` through
unfiltered. The largest `?features=` list anywhere in the suite is **2**. And
`config/settings/test.py` sets `DATABASES["default"]["NAME"] = "mko_bazuna"` and **no
`OPTIONS`**; a repo-wide search for `statement_timeout|lock_timeout|idle_in_transaction_session_timeout`
across `src/` and `docker/` returns **0 hits**.

**Decision required before implementation — Q3: mechanism and value.**

| Option | Mechanism | Consequences |
|---|---|---|
| **(a)** | `DATABASES["default"]["OPTIONS"] = {"options": "-c statement_timeout=N"}` in `config/settings/test.py` | **Gains:** connection-level; applies to **every** test whether or not it wraps a transaction, which is the whole point — the 48 `transaction=True` scopes run unwrapped. No fixture, no teardown, no conftest edit. **Costs:** N is global and must clear the slowest legitimate statement, including `migrate --run-syncdb` in `_restore_test_schema_post_db_setup` and `TRUNCATE … CASCADE` between tests |
| **(b)** | A session-scoped fixture that issues `SET statement_timeout` and `RESET` in teardown | **Gains:** the value can differ per phase of the run and is visible in the fixture. **Costs: it is a fixture in `src/backend/conftest.py`** — the most contended file in the repository, claimed by one phase and forbidden by seven (Q1). It would put BLOCK 5 behind BLOCK 14's blocker for no functional gain |
| **(c)** | `SET LOCAL statement_timeout` in an autouse fixture, as the original report recommended | **REJECTED, and the Implementor must not reinstate it.** `SET LOCAL` **outside** a transaction block is a **no-op** in PostgreSQL. The 48 `transaction=True` scopes — including the entire bot tree — run unwrapped, so a `SET LOCAL` there sets nothing and the runaway query is unbounded precisely where the concurrency tests live. The report's own recommendation was subtly wrong for half the suite |

**The value itself is half the gate.** Two values — the test-side one and DB-004's production
one — drift silently if they are chosen independently. And `N` must clear `TestSearchResponseSLORegression`
(`SEARCH_SLO_MS == 2000` measured by wall clock against a live DB) with headroom, or the
suite's only wall-clock gate starts failing for a reason that has nothing to do with search.

**Binding constraints**

1. **Test configuration only.** `config/settings/test.py` is not production code and this
   block may not edit `config/settings/base.py`, `production.py`, `dev.py` or `local.py`.
2. **No `SET LOCAL`** (option (c) is rejected above; this is stated so it cannot be
   reintroduced as "a cleanup").
3. **No production `statement_timeout`** — that is DB-004's, in phase 03. Two bounds, two
   owners, two commits, and the values reconciled explicitly.
4. **The value must be recorded as a named module constant**, not an inline literal, so
   DB-004's value and this one can be diffed against each other by a human.
5. **No test is added by this block.** The bound and the test it enables are separate commits
   because the test cannot be written before the bound exists — that is BLOCK 6.
6. **`record_event`'s swallowing behaviour is not this block's to change.** If the analytics
   tests red after the bound lands, the answer is "phase 03 `DB-002` has not landed", not
   "widen the timeout until it goes away".

**Implementor task**

```yaml
id: task_11_b05_test_statement_timeout
title: "Bound statements in the test database so a runaway query cannot take it down (11-TEST-003 step 1)"
priority: high
depends_on: [task_11_b01_reconciliation_and_schedule, task_11_b03_hang_bounds]
source_reference: ".ai/plans/11-test-coverage-remediation.md"
source_section: "BLOCK 5 - Bound the test database so a runaway query cannot take it down"
source_blocks: ["BLOCK 5"]
description: >
  config/settings/test.py sets no OPTIONS on DATABASES["default"], and a repo-wide search for
  statement_timeout|lock_timeout|idle_in_transaction_session_timeout across src/ and docker/
  returns 0 hits. The suite therefore cannot host a test that provokes a slow query without
  risking the shared instance - which is very likely why that test was never written. Add a
  connection-level bound under the Q3 option, sized with phase 03 DB-004, after phase 03 DB-002
  has landed. SET LOCAL is explicitly rejected: it is a no-op outside a transaction block, and
  the 48 transaction=True scopes run unwrapped.
goals:
  - "bound every statement in the test database, transactional or not"
  - "add no production bound, no conftest fixture and no test"
  - "name the value so it can be diffed against DB-004's"
files:
  - path: "src/backend/config/settings/test.py"
    targets:
      - type: assignment
        name: DATABASES
    semantic_anchors:
      insert_after:
        type: assignment
        value: 'DATABASES["default"]["NAME"]'
changes:
  - action: modify_config
    description: >
      Add the Q3 mechanism with the Q3 value as a named module constant, and add the OPTIONS
      key to DATABASES["default"].
acceptance_criteria:
  - "a statement exceeding the bound is cancelled in a transaction=True test and in a transactional one"
  - "the fastest gate is green, including test_migrate_locked, test_sweep_*.py, the analytics suite and the bot tree"
  - "migrate --run-syncdb inside _restore_test_schema_post_db_setup completes under the bound"
  - "TestSearchResponseSLORegression is green unchanged"
  - "config/settings/base.py, production.py, dev.py and local.py are untouched"
  - "the commit body names the Q3 option, the value, and DB-004's production value for comparison"
```

---

### BLOCK 6 — The hostile-`?features=` test (`11-TEST-003`, step 2)

| | |
|---|---|
| **Findings owned** | `11-TEST-003` (HIGH), step 2 only |
| **Class** | **coverage** |
| **Depends on** | BLOCK 5 (the bound must exist first — this is the block it exists for) |
| **External gate** | **phase 08 `SRCH-001` BLOCK 1** — the production cap |
| **Priority** | P2 |
| **Risk level** | **MEDIUM–HIGH** — the single highest-consequence test this plan can add, because a badly-shaped one takes the shared PostgreSQL instance offline for every concurrent agent |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four** |

**Decision required before implementation — Q6: whose commit, and which file?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | The test is **specified by phase 11 and committed inside phase 08's `SRCH-001` commit**, together with the production cap | **Gains:** one commit, production + expectation, which is phase 07 VAL-003's rule and the rule four of this phase's findings depend on. No red-on-arrival commit ever exists. **Costs:** phase 11 produces a specification and no code; if phase 08's block is de-scoped, the specification is orphaned |
| **(b)** | Phase 11 commits the test as a **separate commit that is red until phase 08 lands** | **Gains:** phase 11's work is visible and independently reviewable. **Costs: a red commit is a rejected commit** under the one-commit-per-block rule, it sits in the shared history red, and anyone running the fast gate between the two commits sees a failure that is not a defect |
| **(c)** | Phase 11 commits it **after** phase 08's cap has landed | **Gains:** every commit is green. **Costs:** if phase 08's cap already grew the parameter bound in a way that makes the test redundant, the test is a mirror of the implementation — §1.5. And the test is the *detector* for the cap; writing it after the fact means the cap was shipped unverified first |

**The file choice is part of the gate, not an implementation detail.** Phase 08 BLOCK 1 puts
its own bound cases in `apps/search/tests/test_search_view.py::TestSearchViewPublishesFilter`
— a file with **ten phase-08 blocks** plus phase 10 BLOCK 14 in it. The alternative home,
`apps/ads/tests/test_features_filter.py`, carries the AND-semantics cases (3 requests, max 2
slugs) and must **stay green unchanged**. Putting the hostile test in a file ten other blocks
are about to edit is the contention this plan exists to prevent.

**The test must prove it provoked the intended failure.** A `?features=` request that returns
200 because the parameter was silently dropped has tested nothing. The test's own negative
control is part of its acceptance criteria: it must fail against today's uncapped
implementation **with a distinguishable signal** (a cancellation attributable to the bound,
or an explicit cap assertion), and it must not be written so that it passes for a reason
other than the one it exists to check.

**Binding constraints**

1. **Never run the superlinear reproduction against the shared instance.** Phase 08's probe
   terminated the PostgreSQL cluster twice — 22 databases, including 17 xdist worker
   databases, offline. Phase 08's `ANALYZE` numbers are authoritative. This block writes the
   test; **it does not run the reproduction by hand.**
2. **The cap and the `feature_slugs` bound are phase 08's.** This block writes no
   `max_length`, no validator and no join-loop change.
3. **`test_features_filter.py` stays green unchanged** under either file option.
4. **The test must be bounded by BLOCK 5's setting**, and if the two disagree the *test* is
   wrong, not the setting.
5. **No test asserts a timing number.** A wall-clock assertion here would be a second,
   flakier copy of `TestSearchResponseSLORegression`, which CI already runs as a named gate.

**Implementor task**

```yaml
id: task_11_b06_features_bound_test
title: "Specify and land the hostile ?features= regression test (11-TEST-003 step 2)"
priority: medium
depends_on: [task_11_b01_reconciliation_and_schedule, task_11_b05_test_statement_timeout]
source_reference: ".ai/plans/11-test-coverage-remediation.md"
source_section: "BLOCK 6 - The hostile-?features= test"
source_blocks: ["BLOCK 6"]
description: >
  Across the whole test tree only 5 files send a ?features= parameter and the largest list
  anywhere is 2. Add the regression test that a long, hostile slug list cannot take the
  database down, under the Q6 option - which decides whether the commit belongs to this plan
  or to phase 08's SRCH-001 commit. The production cap and any feature_slugs bound are phase
  08's and are not written here. The test must fail, distinguishably, against today's
  uncapped implementation.
goals:
  - "make the runaway-input class observable in the suite"
  - "write no production cap, no DTO bound and no timing assertion"
  - "keep apps/ads/tests/test_features_filter.py green unchanged"
files:
  - path: "src/backend/apps/search/tests/test_search_view.py"
    targets:
      - type: class
        name: TestSearchViewPublishesFilter
  - path: "src/backend/apps/ads/tests/test_features_filter.py"
    targets:
      - type: class
        name: TestFeaturesFilter
changes:
  - action: add_code
    description: >
      Add the hostile-?features= case under the Q6 file option. Assert the observable
      outcome (a bounded response, not a cancelled connection), and include the negative
      control that makes the test fail against today's uncapped implementation.
acceptance_criteria:
  - "the test fails, with a distinguishable signal, against the uncapped implementation"
  - "the test passes under BLOCK 5's bound and phase 08's cap"
  - "apps/ads/tests/test_features_filter.py is green unchanged"
  - "no timing value is asserted and no max_length or validator was added"
  - "the commit body names the Q6 option, the owning commit, and the anchor"
```

---

### BLOCK 7 — The `on_commit` observability scaffold and the rollback-negative tests (`11-TEST-014` + `11-TEST-004`)

| | |
|---|---|
| **Findings owned** | `11-TEST-014` (MEDIUM, new) + `11-TEST-004` (HIGH) items 1–2 |
| **Class** | **coverage** |
| **Depends on** | BLOCK 1 (the schedule names the file owners) |
| **External gate** | **phase 07 `MEDIA-001`** — the scaffold must land with or before it |
| **Priority** | **P1 — the highest-consequence block in this plan** |
| **Risk level** | **HIGH** |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four** |

**Why these two findings are one block.** They share a test-file set and they share a
mechanism. `11-TEST-014` asks *whether an `on_commit` callback can be observed at all*;
`11-TEST-004` asks *whether the deferral and the rollback are tested*. Splitting them puts
the scaffold in one commit and the rollback case in another, and the second is worthless
without the first. They land together.

**The quantified exposure (C-4 — worse than the report states).** The suite is entirely
pytest-style: **0** `TestCase` subclasses, **0** `TransactionTestCase`, **0**
`captureOnCommitCallbacks` / `getOnCommitCallbacks`, and **48** `transaction=True` scopes
across **39** files (bot 24, core 13, ads 3, moderation 3, users 3, currencies 1, search 1).
`pytest.mark.django_db` wraps each test in an `atomic()` block, so `on_commit` never fires
there.

| Production `on_commit` site | Deferred action | Real coverage today |
|---|---|---|
| `apps/users/services/deletion.py` | search cache-version bump | **Yes** — `apps/users/tests/test_deletion.py` has 4 `transaction=True` scopes |
| `apps/media/signals.py` | physical file deletion | **Yes, commit-only** — `test_ad_image_delete_signal.py` (3 tests) + `test_delete_photo_single_call.py` (4 tests) |
| `apps/core/utils/advisory_lock.py` | release log line | **None** — both tests patch `on_commit`. **This file is phase 03 BLOCK 2's** ("it must rewrite the two tests") and is not touched here |
| `apps/moderation/signals.py` | **Telegram alert delivery** | **None** — both sites in `test_approve_ad_side_effects.py` patch `on_commit` with `side_effect=lambda fn: fn()`, inside a module marked `[django_db, integration]`, i.e. transactional, where the callback would never fire anyway |

Two of four production sites — including the one that sends a real Telegram message — are
**structurally unobservable by any test in the repository**. Not under-covered:
*unobservable*.

**Why the media surface is worse than reported.** The report said the `transaction=True`
media surface was `test_ad_image_delete_signal.py` plus "the seven `test_sweep_*.py`
files". Measured: **2 files / 7 tests**. `apps/media/tests/test_sweep_orphaned_media.py` is
**transactional** — its callback never fires. Phase 07's `MEDIA-001` remedy is a reference
check **inside the `on_commit` callback**, and phase 07's VAL-003 independently identified
the three `test_ad_image_delete_signal.py` tests that will break. This block supplies the
reason phase 07 could not state from inside its own layer: **those three are the only tests
in that file that run under `transaction=True`.** A refcount bug inside an `on_commit`
callback has an asymmetric, irreversible failure mode — a false "last reference" deletes
live bytes belonging to another ad, a false "references remain" leaks files silently — and
both are invisible to the eight transactional media test files that make up the bulk of the
surface.

**Decision required before implementation — Q7' (a scheduling question, not a design one):**

Where does the scaffold land relative to phase 07?

| Option | Consequences |
|---|---|
| **(a)** The scaffold **lands before** phase 07's `MEDIA-001` block | **Gains:** MEDIA-001 ships with its verification already in place; phase 07's three broken tests break *into a scaffold that understands why*. **Costs:** `test_ad_image_delete_signal.py` is also held by phase 03 BLOCK 1 and phase 05 BLOCK 13 — a third sequential claimant |
| **(b)** The scaffold is **folded into phase 07's `MEDIA-001` commit** | **Gains:** one commit; the fix and its verification are inseparable by construction, which is the strongest form of the rule. **Costs:** phase 07 owns the test file for a commit, and phase 11's `11-TEST-014` is recorded as satisfied-by-phase-07 |
| **(c)** The scaffold lands **after** `MEDIA-001` | **Gains:** none that the other two do not also give. **Costs:** the half-fix hazard phase 07 VAL-004 warns about, approached from the test side. **This is the option the finding exists to prevent** |

**Binding constraints**

1. **The scaffold's own tests must be inside a `transaction=True` scope, and they must
   prove the callback fired.** A scaffold that looks right and silently never observes the
   `on_commit` is worse than no scaffold, because it converts "unverified" into
   "verified-looking". Each new test carries a sentinel proving execution — a counter, a
   touched file, a written row — not an assertion that nothing happened.
2. **No test in this block may patch `on_commit` away.** Patching it out is the defect
   `11-TEST-004` reports. `test_approve_ad_side_effects.py`'s two existing patches may be
   **replaced** by a real `transaction=True` execution; they may not be left in place beside
   a new real-execution test that contradicts them.
3. **`apps/core/tests/test_advisory_lock_release_log.py` is phase 03 BLOCK 2's.** It is
   read for the shape, never edited. Phase 03 owns lifting the ban and rewriting those two
   tests; this block records the reservation and says so in the commit body.
4. **No rollback test may be written against a scope that cannot roll back.** The rollback
   cases must use a `transaction=True` scope with an explicit `transaction.atomic()` block
   and a raised exception, and must assert the deferred action did **not** fire.
5. **`test_ad_image_delete_signal.py` must stay green unchanged for phase 07's other two
   claimants** — this block adds, it does not rewrite the three existing tests.
6. **`apps/media/tests/test_sweep_orphaned_media.py` is transactional and stays
   transactional.** Adding a `transaction=True` marker to it "so the test passes" would be
   changing another phase's test to suit this block.

**Implementor task**

```yaml
id: task_11_b07_on_commit_scaffold
title: "Add the transaction=True on_commit scaffold and the rollback-negative tests (11-TEST-014, 11-TEST-004)"
priority: high
depends_on: [task_11_b01_reconciliation_and_schedule]
source_reference: ".ai/plans/11-test-coverage-remediation.md"
source_section: "BLOCK 7 - The on_commit observability scaffold and the rollback-negative tests"
source_blocks: ["BLOCK 7"]
description: >
  Zero TestCase subclasses, zero TransactionTestCase, zero captureOnCommitCallbacks, 48
  transaction=True scopes in 39 files. Two of four production transaction.on_commit sites -
  including the Telegram alert delivery in apps/moderation/signals.py - are patched out in
  their only tests, and no rollback-negative test exists anywhere in src/. The media
  transaction=True surface is 2 files / 7 tests, not a sweep surface, so a reference-count
  bug inside apps/media/signals.py's on_commit callback would be verified by 7 tests. Add a
  transaction=True scaffold proving the callback fires, with a sentinel per test, and add the
  rollback-negative cases, before or with phase 07 MEDIA-001.
goals:
  - "make the on_commit callback observable in at least one honest test per production site phase 11 may touch"
  - "add a rollback-negative test that would fail today"
  - "never patch on_commit away in a new test"
files:
  - path: "src/backend/apps/core/tests/test_ad_image_delete_signal.py"
    targets:
      - type: class
        name: TestAdImageDeleteSignal
  - path: "src/backend/apps/core/tests/test_delete_photo_single_call.py"
    targets:
      - type: module
        name: test_delete_photo_single_call
  - path: "src/backend/apps/moderation/tests/test_approve_ad_side_effects.py"
    targets:
      - type: module
        name: test_approve_ad_side_effects
changes:
  - action: add_code
    description: >
      Add the shared-key-not-freed and last-reference-freed media cases inside a
      transaction=True scope, each with a sentinel proving the callback executed. Replace the
      two patched on_commit sites in test_approve_ad_side_effects with a real transaction=True
      execution and add a rollback-negative case for the alert path.
acceptance_criteria:
  - "each new test proves the callback fired; none asserts only an absence"
  - "the rollback cases fail against today's tree and pass after this commit"
  - "no new test patches transaction.on_commit away, and the two existing patches are replaced rather than duplicated"
  - "the three existing tests in test_ad_image_delete_signal.py are green unchanged"
  - "apps/core/tests/test_advisory_lock_release_log.py and apps/media/tests/test_sweep_orphaned_media.py are untouched"
  - "the commit body names the Q7' option and records that phase 03 BLOCK 2 owns the release-log file"
```

---

### BLOCK 8 — The admin generated-form and wired-action contract (`11-TEST-012`)

| | |
|---|---|
| **Findings owned** | `11-TEST-012` (MEDIUM) |
| **Class** | **coverage** |
| **Depends on** | BLOCK 15 (the `cabinet` hub disposition lands alongside) |
| **External gate** | **phase 06 `VAL-007` is mandatory** |
| **Priority** | P2 |
| **Risk level** | **MEDIUM** |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four** |

**The report's premise is refuted; its gap is real.** `apps/core/tests/test_support_admin.py`
(146 lines, `pytest.mark.unit`) **already** carries 12 registered-`ModelAdmin` introspection
tests: `admin.site.is_registered(...)`, `SupportContactAdmin(SupportContact, admin.site)`
and `SupportTicketAdmin(SupportTicket, admin.site)` **instantiated and queried**, and
`list_display` / `list_editable` / `list_filter` / `search_fields` / `readonly_fields`
asserted as class attributes. The report's grep pattern matched neither
`admin.site.is_registered` nor `SupportContactAdmin`, which is a false negative from a
too-narrow search. What survives, verified by exhaustive search:

| Surface | Tested? |
|---|---|
| `ModelAdmin` class attributes (`list_display`, `readonly_fields`, …) | **Yes, for 2 of ~12 admins** |
| Registered-`ModelAdmin` **generated form** (`get_form(request)` → field names, widget classes) | **No admin at all** — `get_form(` returns **0 hits across all of `src/`** |
| Registered-`ModelAdmin` **wired actions** (`get_actions(request)`) | **No admin at all** — `get_actions(` returns **0 hits** |
| Any rendered admin page | **No** — no test issues `Client().get("/admin/…")` |

**Decision required before implementation — Q7: assertion kind and scope.**

| Option | Assertion | Consequences |
|---|---|---|
| **(a)** | **Widget class per field**, from `admin.site._registry[Model].get_form(request)` | **Gains: the only shape that can see `AUT-005` / `PII-103`** — a `password` rendered as `AdminTextInputWidget` fails, and it fails whether the form was auto-built from the absence of `fields`/`fieldsets`/`exclude` or declared. **Costs:** widget classes are Django-version-sensitive; a Django upgrade can change them and turn the test red for a non-reason |
| **(b)** | **Field-name set** per admin | **Gains:** robust across Django versions. **Costs: it cannot see the defect at all** — `UserAdmin` auto-building a form from the *absence* of a declaration exposes exactly the field the test would be checking for. It is the `getsource` failure mode in a new coat |
| **(c)** | Widget class **plus** an explicit declared data-subject column set | **Gains:** (a)'s detection with (b)'s robustness, at the cost of maintaining the set. **Phase 06's `VAL-007` is mandatory under every option:** `test_support_admin.py` already asserts on `SupportContactAdmin.telegram_id`, and a blanket data-subject rule false-positives on a support *channel* id |

**The scope sub-question:** is the rendered-page smoke test
(`Client().get("/admin/<app>/<model>/")` with a staff user) in scope? It is the lowest-value
item of the four, it is the only one that needs a live session and a staff user, and it is
the one most likely to be written so it passes for the wrong reason. The report's own
ordering puts it last. **Under Q7 it may be omitted.**

**Binding constraints**

1. **The assertion is a contract, not a snapshot.** No test in this block may enumerate the
   current field list and call it correct — that is `11-TEST-010`'s failure mode and §1.5's
   question applies verbatim. Assert: identity columns are not writable through a generated
   form; password-bearing fields are not text widgets; every declared `actions` entry is
   reachable through `get_actions(request)`.
2. **`test_support_admin.py` is phase 06 BLOCKs 12/13's file.** This block extends it rather
   than creating a parallel module; the re-read-immediately-before-editing rule applies.
3. **No admin page is rendered under option (a) or (b).** Only the smoke test needs a
   session, and it is optional under Q7.
4. **No production admin is modified.** This block adds tests that may *fail* against a real
   defect (`AUT-005`, `PII-103`, `AD-001`, `PII-107`); it does not fix them. **Those are
   phase 04's, phase 06's and phase 15's.** A test that lands red because it found a real
   defect is *routed*, not deleted — see §6.

**Implementor task**

```yaml
id: task_11_b08_admin_form_contract
title: "Extend the admin introspection to generated forms and wired actions (11-TEST-012)"
priority: medium
depends_on: [task_11_b01_reconciliation_and_schedule, task_11_b15_zero_coverage_triage]
source_reference: ".ai/plans/11-test-coverage-remediation.md"
source_section: "BLOCK 8 - The admin generated-form and wired-action contract"
source_blocks: ["BLOCK 8"]
description: >
  get_form( and get_actions( return 0 hits across all of src/ and no test issues a
  Client().get on an admin URL. apps/core/tests/test_support_admin.py already introspects
  two registered ModelAdmins at the class-attribute level; extend it to the generated form
  and the wired actions under the Q7 option. The assertion must be a contract - identity
  columns not writable through a generated form, password-bearing fields not text widgets,
  every declared action reachable - never a snapshot of the current field list.
goals:
  - "make the generated form and the wired actions observable for every registered ModelAdmin"
  - "assert a contract, not a snapshot of today's field list"
  - "modify no production admin"
files:
  - path: "src/backend/apps/core/tests/test_support_admin.py"
    targets:
      - type: module
        name: test_support_admin
      - type: class
        name: SupportContactAdmin
  - path: "src/backend/apps/core/admin.py"
    targets:
      - type: class
        name: AdminSite
    semantic_anchors: {}
changes:
  - action: add_code
    description: >
      Add the Q7-scoped generated-form contract over every registered ModelAdmin, and the
      get_actions(request) contract for every admin declaring actions. Read-only on
      apps/core/admin.py and every other admin module.
acceptance_criteria:
  - "every registered ModelAdmin's generated form is inspected and its identity columns and password-bearing fields are asserted non-writable"
  - "every admin declaring actions is asserted to have them reachable through get_actions(request)"
  - "SupportContactAdmin.telegram_id does not false-positive, per phase 06 VAL-007"
  - "no assertion enumerates today's field list as correct"
  - "any test that fails on arrival is routed to its owning phase in the commit body, not deleted"
  - "no production admin module was modified"
```

---

### BLOCK 9 — The C0 / NUL hostile-input corpus for `?q=` (`11-TEST-006`)

| | |
|---|---|
| **Findings owned** | `11-TEST-006` (MEDIUM) |
| **Class** | **coverage** |
| **Depends on** | BLOCK 1 (the schedule; `test_search_view.py` has 12 claimants) |
| **External gate** | **phase 08 BLOCK 3** — the `NUL → 500` production fix |
| **Priority** | P2 |
| **Risk level** | **MEDIUM** — file contention, not test-design risk |
| **Required agents** | **Auditor · Planner · Validator.** Researcher not required |

**Confirmed.** `apps/search/tests/test_search_view.py::TestSearchViewInputRobustness` exists
with exactly three tests: `test_query_exceeding_max_length_returns_200`,
`test_sql_injection_query_returns_200`, and
`test_homoglyph_and_control_chars_query_returns_200` — whose payload is `Транспорт` +
**U+200B** + `<script>`. U+200B is a **format-class invisible character**, not C0. No
`\x00` and no C0 control character reaches any `?q=` test.

**The report's grep evidence is false, and that makes the finding stronger.** It states that
a search for `x00|\u0000|NUL|null byte` returns zero test hits. Two real NUL tests exist:
`apps/ads/tests/test_media_security.py::test_path_traversal_with_null_byte` and
`apps/media/tests/test_filesystem.py::test_rejects_nul_byte`. Both are on the **media** path,
not the `?q=` path. **The project demonstrably knows about NUL-byte hostility in one subsystem
and has not carried that discipline into search.**

**This is a test-expectation change and it must land in the same commit as its production
change.** A `\x00` in `?q=` raises `DataError` on `/search/` **and** on
`/api/search/autocomplete` today — phase 08 has already validated the 500. Writing the test
in phase 11 and the fix in phase 08 produces two commits, one of them red.

**File contention — the sharpest in this plan.** `test_search_view.py` is claimed by **ten
phase-08 blocks** (1, 3, 4, 5, 6, 7, 9, 10, 11, 12), **one phase-10 block** (14, the
`build_listincontext` extraction), and this block. **The ordering rule, fixed once in BLOCK
1 and repeated here:** *phase 08 BLOCK 3 → phase 10 BLOCK 14 → phase 11 BLOCK 9.* A block
that does not get its turn **must re-read this file and both other plans immediately before
editing**, and must stop and report if the file has uncommitted changes from another agent.

**Binding constraints**

1. **The test lands with phase 08's fix, or not at all.** A red-on-arrival commit is a
   rejected commit.
2. **The parametrised cases must assert an observable outcome**, HTTP 200 and a result set,
   not an absence of an exception. Asserting `pytest.raises(DataError)` would be a test that
   encodes the defect as the expected behaviour — project rule 2, restated.
3. **The class must not be split.** `TestSearchViewInputRobustness` is the hostile-input
   home; adding a parallel class in the same file creates two places to look.
4. **`/api/search/autocomplete` is in scope** for the same payload, because phase 08
   validated the `DataError` on both paths. Whether it is asserted here or in phase 08's
   commit is a coordination detail recorded in the commit body, not a silent choice.
5. **No production search code is edited by this block.**
6. **`test_search_query_count.py` and `test_search_slo.py` are not edited** by this block —
   they are the tripwires that detect whether the corpus change altered a query count or a
   wall-clock gate.

**Implementor task**

```yaml
id: task_11_b09_q_hostile_corpus
title: "Extend the search input-robustness corpus with C0 and NUL cases (11-TEST-006)"
priority: medium
depends_on: [task_11_b01_reconciliation_and_schedule]
source_reference: ".ai/plans/11-test-coverage-remediation.md"
source_section: "BLOCK 9 - The C0 / NUL hostile-input corpus for ?q="
source_blocks: ["BLOCK 9"]
description: >
  TestSearchViewInputRobustness has exactly three tests and the third uses U+200B, a
  format-class character, not C0. No NUL and no C0 control character reaches any ?q= test,
  although two NUL tests already exist on the media path. Add a parametrised C0 case
  asserting HTTP 200 and a result set, in the same commit as phase 08's production fix.
  test_search_view.py is the most contended test file in the plan set - ten phase-08 blocks
  plus one phase-10 block - so the file must be re-read immediately before editing.
goals:
  - "cover the C0/NUL class on the search input path"
  - "assert an observable outcome, never the current DataError"
  - "touch no production search code"
files:
  - path: "src/backend/apps/search/tests/test_search_view.py"
    targets:
      - type: class
        name: TestSearchViewInputRobustness
    semantic_anchors:
      insert_before:
        type: function
        value: test_query_exceeding_max_length_returns_200
  - path: "src/backend/apps/ads/tests/test_media_security.py"
    targets:
      - type: function
        name: test_path_traversal_with_null_byte
    semantic_anchors: {}
changes:
  - action: add_code
    description: >
      Add the parametrised C0 case to TestSearchViewInputRobustness, covering %00, %01, %0a
      and %1b, asserting HTTP 200 and zero results. Read-only on the media NUL tests.
acceptance_criteria:
  - "each C0 case asserts HTTP 200 and a result set, not an exception"
  - "the suite does not contain pytest.raises(DataError) on any ?q= path"
  - "test_search_query_count.py and test_search_slo.py are green unchanged"
  - "the file was re-read and phase 08's and phase 10's plans re-checked immediately before editing"
  - "the commit body names the phase-08 commit this lands with"
```

---

### BLOCK 10 — Two-writer dedup coverage for `PopularSearch` / `SearchHistory` (`11-TEST-007`)

| | |
|---|---|
| **Findings owned** | `11-TEST-007` (MEDIUM), items 2 and 3 only |
| **Class** | **coverage** |
| **Depends on** | BLOCK 1 (the schedule) |
| **External gate** | **phase 08 BLOCK 5** — the `UniqueConstraint` and its migration |
| **Priority** | P2 |
| **Risk level** | **MEDIUM** |
| **Required agents** | **Auditor · Planner · Validator.** Researcher required for the two-thread interleaving design |

**Confirmed exactly.** `PopularSearch.query_normalized` is
`CharField(max_length=200, db_index=True)` — **no `unique=True`**. `PopularSearch.Meta`
carries only `db_table = "popular_searches"` and **no `constraints`**.
`SearchHistory.query_normalized` is identical in shape. The dedup is a plain
`PopularSearch.objects.get_or_create(query_normalized=…, defaults=…)` followed by an `F()`
increment; `search_history.py` does `delete()` then `create()`. Under READ COMMITTED — the
level phase 03 confirmed is in use — two concurrent `get_or_create` calls on a non-unique
column can both miss and both insert. The three existing dedup tests in
`apps/search/tests/test_autocomplete.py` are sequential, single-threaded, inside one
transaction: they prove the counter increments, and they cannot interleave.

**What is phase 08's and is not re-filed here.** The `UniqueConstraint` on
`PopularSearch.query_normalized` plus the migration, and the `MultipleObjectsReturned` 500 it
produces, are phase 08 BLOCK 5's. **This block must not create a constraint, a migration, or
a second `UniqueConstraint`.** `makemigrations --check` after this block must report **no
changes**.

**Decision required before implementation — Q7'' (scope, and the red-commit problem).**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | The `Meta.constraints` introspection test is **specified by phase 11 and committed inside phase 08 BLOCK 5's commit**, beside the constraint it asserts | **Gains:** the test is green in the commit that introduces the constraint; there is never a moment where the constraint exists and is unasserted. **Costs:** phase 11 produces a specification and no code for this item |
| **(b)** | The introspection test commits **after** phase 08's migration | **Gains:** phase 11's code exists and is reviewable. **Costs:** for the interval between the two, the constraint ships unverified — which is precisely the gap the finding reports, re-created one commit later |
| **(c)** | Only the `transaction=True` two-thread test ships from phase 11; the introspection test is deferred | **Gains:** the concurrency half does not depend on phase 08 at all and can ship immediately. **Costs:** the constraint-introspection half — item 2, the one that would catch a dropped constraint — is deferred to whoever owns the constraint |

**The two-thread test has a design question the Implementor may not answer silently.** A
`transaction=True` two-thread dedup test needs its two writers to actually interleave, and
the existing `test_lookup_cache_swr.py` pattern (`time.sleep(0.2)` to force overlap) is
**timing-dependent by construction**. Whether to force overlap with a sleep, with a
`threading.Event`, or with a lock the production code does not have, is a real choice: a
sleep makes the test timing-dependent; an event makes it deterministic but must not require
production cooperation.

**Binding constraints**

1. **No model change, no migration, no constraint.** `makemigrations --check` reports no
   changes after this block. The suite has **zero** `skip` / `skipif` / `xfail` markers and
   this block does not introduce the first one — a conditional introspection test would be a
   test that can silently stop running.
2. **The introspection test asserts the constraint's *presence and semantics*, not its
   literal `name`.** A `name` assertion is a snapshot that turns red on a rename.
3. **The two-thread test must be deterministic or honestly timing-dependent.** If it uses a
   sleep, the commit body says so, because that is a maintenance cost the next reader
   inherits.
4. **`test_autocomplete.py` is a phase-08-adjacent file**; re-read before editing.
5. **No assertion may rely on catching `MultipleObjectsReturned`** as the pass condition —
   that encodes the current defect as expected behaviour (project rule 2, restated).

**Implementor task**

```yaml
id: task_11_b10_dedup_coverage
title: "Cover PopularSearch/SearchHistory dedup under two writers (11-TEST-007 items 2-3)"
priority: medium
depends_on: [task_11_b01_reconciliation_and_schedule]
source_reference: ".ai/plans/11-test-coverage-remediation.md"
source_section: "BLOCK 10 - Two-writer dedup coverage for PopularSearch / SearchHistory"
source_blocks: ["BLOCK 10"]
description: >
  PopularSearch.query_normalized has no unique=True, PopularSearch.Meta carries only db_table
  and no constraints, and the dedup is a plain get_or_create under READ COMMITTED - so two
  concurrent writers can both miss and both insert. The three existing dedup tests in
  test_autocomplete.py are sequential and single-threaded. Add the two-thread transaction=True
  test, and specify the Meta.constraints introspection test for phase 08's migration commit.
  Item 1 - the UniqueConstraint and its migration - is phase 08 BLOCK 5's and is not written
  here.
goals:
  - "cover the two-writer interleaving the three sequential tests cannot reach"
  - "ship no model change, no migration and no constraint"
  - "introduce no skip, skipif or xfail marker"
files:
  - path: "src/backend/apps/search/tests/test_autocomplete.py"
    targets:
      - type: module
        name: test_autocomplete
  - path: "src/backend/apps/search/models.py"
    targets:
      - type: class
        name: PopularSearch
      - type: class
        name: SearchHistory
    semantic_anchors: {}
changes:
  - action: add_code
    description: >
      Add a transaction=True two-thread dedup test beside the three existing ones. Read-only
      on models.py. Under Q7'' option (b) or (c), also add the Meta.constraints introspection
      test asserting the constraint's fields and semantics without asserting its name.
acceptance_criteria:
  - "the two-thread test fails or is demonstrably distinguishable against a non-unique column and passes against a unique one"
  - "makemigrations --check reports no changes"
  - "no skip, skipif or xfail marker was introduced anywhere in the suite"
  - "the introspection test, if written, asserts fields and semantics and not the constraint name"
  - "no assertion expects MultipleObjectsReturned"
  - "the commit body names the Q7'' option and states whether the test is timing-dependent"
```

---

### BLOCK 11 — The rule for the 27 source-text assertions (`11-TEST-010`)

| | |
|---|---|
| **Findings owned** | `11-TEST-010` (MEDIUM) |
| **Class** | **coverage + reconciliation** |
| **Depends on** | **BLOCK 8** — the rule names what BLOCK 8's contract tests replace |
| **Priority** | P2 |
| **Risk level** | **MEDIUM** — the failure mode is deleting the only guard on a locking structure |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four** |

**Confirmed exactly: 27 `inspect.getsource` occurrences across exactly 8 files**, with two
path corrections (C-5). The critique is correct and sharp: the assertions check that
substrings occur somewhere in a module's text, so they **pass whether the code works or is
entirely broken**, and fail on an equivalent refactor.

**The instructive case is the strongest part of the finding.**
`apps/users/tests/test_admin_pii_containment.py` is the **only** test file that audits the
admin surface, and it is built entirely from `getsource` checks on `list_display` helpers.
`AUT-005` / `PII-103` (`UserAdmin` auto-building a `ModelForm` with `password` as a
plain-text `CharField`) lives in the **absence** of `fields`/`fieldsets`/`exclude` — there is
no source text to grep. The same is true of `AD-001` (`status` missing from
`readonly_fields`). **A source-text test cannot see a defect expressed as an absence**, which
is why phase 04's validator and phase 06's auditor both had to reach for registered-`ModelAdmin`
form introspection to find it.

**And the counter-example, which is why a blanket deletion is wrong.**
`apps/core/tests/test_migrate_locked.py::TestSessionLockLogging` is a `getsource` test that
**earns its place**: phase 01 shipped it as a hard regression guard for a log line that is the
*product* of the fix. `apps/telegram_bot/tests/test_unsubscribe.py::TestResolveOwnedLocking`'s
two order assertions pin that the lock is acquired before the ownership check. Both assert
something a *behavioural* test cannot easily assert — the **presence of a specific
architectural element** — which is a legitimate use of source inspection.

**Decision required before implementation — Q8: the rule.**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Keep all 27 | **Gains:** no risk. **Costs:** leaves the mirror-test class in place, leaves `test_admin_pii_containment.py` as the only admin audit, and leaves a rule nothing enforces. The finding is not addressed |
| **(b)** | Write the rule, keep the cross-tree invariants and the shipped regression guards, and **delete only `test_admin_pii_containment.py`'s four substring assertions** — after BLOCK 8's generated-form contract covers what they were reaching for | **Gains:** the module's *purpose* (auditing the admin surface) is preserved by a stronger mechanism; the mirror style leaves; `TestSessionLockLogging` and the lock-order assertions survive. **Costs:** depends on BLOCK 8; if BLOCK 8 is de-scoped, the deletion is unopposed and the admin surface loses its only audit |
| **(c)** | Delete all 27 | **Gains:** a clean sweep. **Costs: it deletes a shipped phase-01 hard regression guard and two lock-order assertions**, across files five other phases are holding (`test_edit_views_locking.py` ×7, `test_admin_actions.py` ×5, `test_migrate_locked.py` ×4, `test_moderation_views.py` ×3). **The Implementor may not choose this** |

**Binding constraints**

1. **The rule is written down before any assertion is touched**, and it is committed. A rule
   nobody can point at is a rule that gets re-litigated every time the next phase opens this
   file.
2. **No assertion may be deleted unless the rule says so and the commit body names which
   category it fell into.**
3. **The three AST-source tests are a different class and are not in scope**: they assert
   cross-tree *invariants* (`AdvisoryLockId` resolution, bot locale bypasses, migration-file
   shape), which is the accepted house style the code context names. They are not "string
   matching" and this block does not touch them.
4. **The two structural source-inspection tests** (`test_sweep_lock_structure.py`, phase 05's
   `TestBulkLockingStructure`) are **not** in scope either: they assert *where* a lock is
   imported from, which is architectural placement, not implementation text.
5. **No block deletes a test to make another phase's change green** — that is the standing
   failure mode of this class. §1.3 rule 3 and §7.

**Implementor task**

```yaml
id: task_11_b11_getsource_rule
title: "Write and apply the rule for the 27 source-text assertions (11-TEST-010)"
priority: medium
depends_on: [task_11_b01_reconciliation_and_schedule, task_11_b08_admin_form_contract]
source_reference: ".ai/plans/11-test-coverage-remediation.md"
source_section: "BLOCK 11 - The rule for the 27 source-text assertions"
source_blocks: ["BLOCK 11"]
description: >
  27 inspect.getsource substring assertions across 8 files pass whether the code works or is
  entirely broken, and fail on an equivalent refactor. test_admin_pii_containment.py is the
  extreme case - 4 assertions, the whole module, and the only admin-surface audit in the
  suite - and cannot see AUT-005/PII-103 because that defect is expressed as an absence.
  Write the rule first, then apply the Q8 option. test_migrate_locked.py::TestSessionLockLogging
  is a source-text test that earns its place and must survive.
goals:
  - "write a rule that distinguishes a legitimate architectural assertion from a mirror"
  - "delete only the assertions the rule identifies, naming each in the commit body"
  - "preserve every shipped regression guard and every cross-tree AST invariant"
files:
  - path: "src/backend/apps/users/tests/test_admin_pii_containment.py"
    targets:
      - type: module
        name: test_admin_pii_containment
  - path: "src/backend/apps/core/tests/test_migrate_locked.py"
    targets:
      - type: class
        name: TestSessionLockLogging
    semantic_anchors: {}
  - path: "src/backend/apps/ads/tests/test_edit_views_locking.py"
    targets:
      - type: module
        name: test_edit_views_locking
  - path: "src/backend/apps/moderation/tests/test_admin_actions.py"
    targets:
      - type: module
        name: test_admin_actions
changes:
  - action: modify_code
    description: >
      Commit the rule first, then apply the Q8 option. Do not touch the AST-source tests or
      the two structural lock-placement tests.
acceptance_criteria:
  - "the rule is written down in the commit body and classifies each of the 27 assertions"
  - "TestSessionLockLogging, TestResolveOwnedLocking's two order assertions and all three AST-source tests are green and unmodified"
  - "any deleted assertion is named individually with its category"
  - "BLOCK 8's generated-form contract covers what test_admin_pii_containment.py was reaching for, or the deletion did not happen"
  - "the diff contains no source file outside tests/"
```

---

### BLOCK 12 — Behavioural cross-process assertions (`11-TEST-005`)

| | |
|---|---|
| **Findings owned** | `11-TEST-005` (MEDIUM, narrowed) |
| **Class** | **coverage** |
| **Depends on** | BLOCK 1 (the schedule) |
| **External gate** | **phase 04** (`AUT-002` session/account-state divergence) and **phase 06** (`PII-104` alert audience predicate) — the predicate-equality test is meaningless before the predicates exist |
| **Priority** | P2 |
| **Risk level** | **MEDIUM** |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four** |

**What actually survives of the report's headline.** Two of its three claims are refuted:

- *"Zero tests cross the web/bot boundary in either direction"* — **false**. Bot side: eight
  `django.test` imports, all `override_settings`, zero `Client(`/`RequestFactory`/`ASGIRequest`,
  so *"no bot test issues a web request"* is the narrow true claim. Backend side: there are
  **21** hits and **at least five are real cross-tree tests** — `test_advisory_lock_ids.py`
  (AST + regex over both trees), `test_i18n_completeness.py` (AST scan of the bot tree),
  `test_thumbnail_integration.py`, `test_docs_ci_parity.py`, `test_ci_security.py` — plus
  `src/telegram_bot/tests/test_contact_gate.py`, which proves both processes delegate to the
  same `_check_seller_contactable` helper.
- *"Threads cannot model two connections"* — **largely false**. `test_edit_views_locking.py`
  and the sweep/bulk concurrency tests use `threading.Thread` under
  `django_db(transaction=True)`; Django gives each thread its own connection and transaction,
  so the two-independent-snapshots interleaving **is** what they exercise. The asgiref
  `thread_sensitive` worker concern — the specific mechanism the report was worried about — is
  covered by `apps/core/tests/test_db_connection_middleware.py` (phase 03's `DB-001`). The
  bot tree carries **24 `transaction=True` scopes and 18 files pinned to
  `xdist_group("bot_concurrent")`**.

**The residual is narrow, real, and additive.** No test asserts that a state written by one
process is observed by the other **at the behavioural level**: after the bot's `submit_ad`
publishes an ad, nothing asserts `/search/` or `/ads/<id>/` returns it with the right city,
price and denormalised `category_name`; and after a web-side `ad_edit`, nothing asserts the
bot's "my ads" listing or `AccountStateMiddleware` view reflects it. That is the class in which
`AUT-002` and `PII-104` live.

**Two shapes ship here:**

1. **Behavioural cross-process observation** — bot side: `sync_to_async(ORM)` assertion (the
   pattern already exists everywhere); web side: a `Client` request asserting the observable
   fields. ~6 tests.
2. **Predicate equality** — the same row evaluated by a bot-side predicate and a web-side
   predicate returns the same set. **This is a shared-predicate test, not a concurrency test**,
   and it is gated on both predicates existing.

**Decision required before implementation — Q8' (the bot-side ORM rule).** Every DB call from
a bot test must go through `sync_to_async(...)`, because the bot suite's asgiref worker thread
owns a **separate** Django connection. A new bot test that calls the ORM directly will
**deadlock or corrupt teardown, not fail cleanly**. Which of the two shapes uses the bot side
and which uses the web side is a real choice with different fixture consequences
(`sync_to_async(User.objects.get_or_create)` is the existing idiom; the web side needs a
`Client` session, which `src/telegram_bot/tests/conftest.py` does not provide and this plan
does not add).

**Binding constraints**

1. **The real bot process is not run inside pytest.** The report's proposal 3 is **endorsed**
   and is a binding constraint: that would be the overengineering the project rules warn
   against, and no block may build a harness for it.
2. **No new bot fixture.** `src/telegram_bot/tests/conftest.py` is a full redefinition with
   ten fixtures and two connection reapers; adding one is a change to the most delicate
   fixture file in the repository for a test that should fit an existing shape.
3. **The assertion is on observable fields**, not on the ORM path. City, price and
   denormalised `category_name` are what a cross-process divergence actually breaks.
4. **The predicate-equality test may not ship before both predicates are landed.** A test
   asserting that two currently-divergent predicates agree would be asserting a defect as
   correct — project rule 2, restated.
5. **No shared-database, cross-process, two-`pytest`-invocation harness.** Both shapes run
   inside one process against one database; that is the architecture's actual boundary and
   the tests must respect it.

**Implementor task**

```yaml
id: task_11_b12_cross_process_assertions
title: "Add behavioural cross-process and predicate-equality assertions (11-TEST-005)"
priority: medium
depends_on: [task_11_b01_reconciliation_and_schedule]
source_reference: ".ai/plans/11-test-coverage-remediation.md"
source_section: "BLOCK 12 - Behavioural cross-process assertions"
source_blocks: ["BLOCK 12"]
description: >
  Helper delegation and CI parity are already tested; behaviour is not. Add the behavioural
  cross-process assertions - after the bot's submit_ad publishes an ad, a web-side Client
  request returns it with the right city, price and denormalised category_name, and a
  web-side ad_edit is visible to the bot's listing - plus the predicate-equality test for
  the AUT-002 / PII-104 shape, gated on both predicates being landed. Every bot-side DB call
  goes through sync_to_async. The real bot process is not run inside pytest.
goals:
  - "cover the behavioural half of the web/bot boundary"
  - "add no fixture, no harness and no cross-process runner"
files:
  - path: "src/backend/apps/ads/tests/test_ad_lifecycle.py"
    targets:
      - type: module
        name: test_ad_lifecycle
  - path: "src/backend/apps/ads/tests/test_edit.py"
    targets:
      - type: module
        name: test_edit
  - path: "src/telegram_bot/tests/test_ad_lifecycle.py"
    targets:
      - type: module
        name: test_ad_lifecycle
    semantic_anchors: {}
changes:
  - action: add_code
    description: >
      Add the behavioural assertions under the Q8' shape choice, using sync_to_async for every
      bot-side ORM call. Read-only on src/telegram_bot/tests/conftest.py.
acceptance_criteria:
  - "each assertion is on observable fields - city, price, denormalised category_name - not on an ORM path"
  - "every bot-side database call goes through sync_to_async and no direct ORM call deadlocks teardown"
  - "no new fixture was added to either conftest"
  - "the real bot process is not started by any test"
  - "the predicate-equality test ships only if both predicates are landed; otherwise it is routed, not written"
```

---

### BLOCK 13 — Effect tests for the four real data migrations (`11-TEST-011`)

| | |
|---|---|
| **Findings owned** | `11-TEST-011` (MEDIUM) |
| **Class** | **coverage** |
| **Depends on** | BLOCK 1 (the schedule) |
| **External gate** | **phase 02** — it holds `apps/core/tests/test_migrations.py` via BLOCKs 3/4/5/9 and `config/settings/test_migrations.py` |
| **Priority** | P2 |
| **Risk level** | **MEDIUM** |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four** |

**Mechanism confirmed.** `config/settings/test.py` defines `class DisableMigrations:` —
**not** a `dict` subclass; the report's quote of `class DisableMigrations(dict):` is wrong,
which is a signal that the evidence was reconstructed rather than copied. `MIGRATION_MODULES =
DisableMigrations()` means pytest-django builds the test schema by **`syncdb`**, and
`src/backend/conftest.py::_restore_test_schema_post_db_setup` re-applies what `syncdb`
cannot create. `apps/core/tests/test_migrations.py` asserts migration **applicability** and
**idempotency**, in a subprocess under `config.settings.test_migrations` with
`@pytest.mark.settings` and `xdist_group("migrations")` — **never effect**.

**Correction (C-7):** there is no squash *migration*; the
`apps/core/management/commands/squash_rehydrate_runsql.py` **command** exists and is fully
tested by `apps/core/tests/test_squash_rehydrate_runsql.py` (4 tests). The search vector is
maintained by a PostgreSQL trigger, never a `RunPython` backfill. The report's "both named
targets are absent" is half wrong.

**The four real targets, and why each matters:**

| Migration | Ops | Why an effect test matters |
|---|---|---|
| `apps/ads/migrations/0003_dedup_per_user_drafts.py` | 2 | **Destructive** — deletes duplicate per-user DRAFTs. A silent no-op leaves duplicates forever and `0004_ad_uq_ads_single_draft_per_user` then **fails to apply**. This is the highest-value target in the set, and the pair together are the argument for testing effect |
| `apps/search/migrations/0002_redact_search_queries.py` | 2 | Rewrites production rows (PII redaction). A silent no-op leaves unredacted phone numbers and e-mails in the table |
| `apps/core/migrations/0003_add_bot_username.py` | 2 | Backfills a user column |
| `apps/core/migrations/0002_seed_default.py` | 1 | Seeds a reference row |

**The trap this block exists to avoid.** Writing a data-migration-effect test in the **default**
suite would be wrong and would silently pass for the wrong reason: the default suite's schema
is a `syncdb` of *current* models, so the migration's preconditions do not exist and the
forward migration is a no-op that "passes". The effect test must use the **subprocess shape**
`apps/core/tests/test_migrations.py` already establishes — `config.settings.test_migrations`
and the `test_migration_repro` database — because that path builds the schema by **migrating**,
not by `syncdb`.

**Decision required before implementation — Q9: which targets, and on what database.**

| Option | Consequences |
|---|---|
| **(a)** | **`ads/0003` + `ads/0004` only**, on the existing `test_migration_repro` database and subprocess shape. **Gains:** the highest-value target, and it is the pair with a provable causal link — the dedup's effect is exactly `0004`'s precondition. **Costs:** leaves the PII rewrite and the two core backfills untested |
| **(b)** | **All four**, same database and shape | **Gains:** closes the class. **Costs:** four subprocess round-trips per run in the `migrations` xdist group; a failure in one is harder to attribute |
| **(c)** | **`ads/0003` and `search/0002` only** — the two with a destructive or irreversible consequence | **Gains:** best consequence-per-runtime ratio; the two core backfills are additive and idempotent-ish, so a silent no-op there costs less. **Costs:** leaves a known gap that a future reader must rediscover |

**The database sub-question matters.** Reusing `test_migration_repro` means sharing a
database with phase 02's blocks and with `test_migrations.py`'s own subprocesses. A new
database is cleaner and slower. The choice is part of Q9, not an implementation detail.

**Binding constraints**

1. **No effect test in the default suite.** If the test does not run under
   `config.settings.test_migrations` against `test_migration_repro`, it is not an effect test
   and it does not ship — it will pass for the wrong reason.
2. **No production data is touched.** The subprocess runs against a test database; the block
   must name the database it targets and assert it is the repro one.
3. **No migration is created, altered or deleted.** Phase 11 ships none.
4. **The assertion is on the database state, not on the migration's return value.**
   "One DRAFT per user remains", "`PopularSearch.query` carries no digits from the original"
   — not "the function returned".
5. **`test_migrations.py` is phase 02's.** This block **extends** the shape and does not
   rewrite the existing applicability and idempotency tests.

**Implementor task**

```yaml
id: task_11_b13_migration_effect_tests
title: "Assert the effect of the real data migrations (11-TEST-011)"
priority: medium
depends_on: [task_11_b01_reconciliation_and_schedule]
source_reference: ".ai/plans/11-test-coverage-remediation.md"
source_section: "BLOCK 13 - Effect tests for the four real data migrations"
source_blocks: ["BLOCK 13"]
description: >
  The test schema is a syncdb of current models, so no data migration's effect is ever
  exercised; test_migrations.py asserts applicability and idempotency only. Add effect tests,
  through the existing subprocess shape under config.settings.test_migrations, for the Q9
  target set - with ads/0003_dedup_per_user_drafts as the primary target because its effect is
  the precondition for ads/0004's UNIQUE constraint, and search/0002_redact_search_queries
  because a silent no-op leaves unredacted PII in the table.
goals:
  - "make the effect of the destructive and PII-rewriting migrations observable"
  - "run every effect test against the migration database, never the syncdb schema"
  - "create, alter and delete no migration"
files:
  - path: "src/backend/apps/core/tests/test_migrations.py"
    targets:
      - type: module
        name: test_migrations
  - path: "src/backend/apps/ads/migrations/0003_dedup_per_user_drafts.py"
    targets:
      - type: function
        name: forwards
    semantic_anchors: {}
  - path: "src/backend/apps/ads/migrations/0004_ad_uq_ads_single_draft_per_user.py"
    targets:
      - type: module
        name: "0004_ad_uq_ads_single_draft_per_user"
  - path: "src/backend/apps/search/migrations/0002_redact_search_queries.py"
    targets:
      - type: function
        name: forwards
    semantic_anchors: {}
changes:
  - action: add_code
    description: >
      Add the Q9 target set's effect tests using the existing subprocess and settings shape.
      Read-only on every migration file. Do not modify the existing applicability or
      idempotency tests.
acceptance_criteria:
  - "each effect test runs against the migration database and names it"
  - "after a forward migrate of ads/0003 exactly one DRAFT per user remains, and ads/0004's constraint applies"
  - "after a forward migrate of search/0002 the redacted column carries no original digits"
  - "the existing applicability and idempotency tests are green unchanged"
  - "no migration file was created, altered or deleted"
  - "the commit body names the Q9 option and the database the tests target"
```

---

### BLOCK 14 — The `create_test_ad` contract (`11-TEST-001`)

| | |
|---|---|
| **Findings owned** | `11-TEST-001` (HIGH) |
| **Class** | **coverage** — test code only; **no production code is touched** |
| **Depends on** | BLOCK 1 (which carries Q1 and Q2) |
| **External gate** | **Q1 — coordinator — BLOCKER** · **Q2 — phase 05 owner + coordinator — BLOCKER** |
| **Priority** | **P0 — but it cannot start until both blockers are answered** |
| **Risk level** | **HIGH** |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four** |

**What is confirmed.** `create_test_ad(..., status: AdStatus = AdStatus.ON_MODERATION, ...)`
and `create_test_ads_bulk(..., status: AdStatus = AdStatus.ON_MODERATION, ...)` in
`src/backend/conftest.py`. `ON_MODERATION` is never committed by any production writer:
`submit_ad` calls `ad.transition_to(ON_MODERATION)` inside the `atomic()` opened for the
submission and then calls `auto_moderate(ad)` **inside the same block**, and `ad_reactivate`
does the same; `auto_moderate()` has no third exit — every path returns through
`_pass_moderation` or `_fail_moderation`. **The fixture fabricates a durable state that
production cannot produce.**

**The count (C-1): 124 sites in 22 files** — 62 explicit, 62 defaulted. The defaulted count
is **stable across both anchors**, which is the reassuring part: the mechanical pass is still
exactly 62 edits. See §0.2.3 for the per-file table.

**Correction the Implementor must know (C-9).** Phase 05 BLOCK 4 finding 1 states that
`src/telegram_bot/tests/conftest.py` **redefines** `create_test_ad` and `create_test_ads_bulk`
and that "both conftests must change together … this is a **hard** requirement". **That is
factually wrong.** The bot conftest does **not** redefine the factories — its own docstring
says *"`create_test_ad` IS shared: it is imported from the backend conftest via `from
conftest import create_test_ad` (resolved through `pythonpath`)"*. It **does** fully redefine
the eight fixtures, because pytest's upward conftest discovery never passes through
`src/backend/` from `src/telegram_bot/`. **One default change in `src/backend/conftest.py`
reaches both trees.** Acting on phase 05's claim would edit a file that does not need editing.

**Decision required before implementation — Q1: who edits `src/backend/conftest.py`?**

This is the most contended file in the repository. Seven plans forbid it; one claims it.

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | **Fold `11-TEST-001` into phase 05 BLOCK 4** and record the finding as *closed by phase 05* | **Gains:** the claim phase 05 already filed is honoured; six plans' "nobody" statements stay true; the fixture default and `AD-008` land in one story. **Costs:** phase 05's BLOCK 4 mandatory internal order assumes its own census and triage, and phase 11's finding disappears from phase 11's record unless explicitly cross-referenced |
| **(b)** | **Carve `11-TEST-001` out as a phase-11 exception**, sequenced **after** `AD-008` is decided | **Gains:** the finding keeps its own owner, its own commit history and its own gate; the 62-site pass is *mechanically* separable from `AD-008`'s production decision. **Costs:** a seventh plan now edits the file, against six that say nobody |
| **(c)** | **Defer** until phase 05 BLOCK 4 has landed, then act only if the default is still wrong | **Gains:** zero contention. **Costs: if phase 05 BLOCK 4 is de-scoped, nothing happens and the fixture keeps lying** — the finding is never closed and the two documentation files stay wrong |

**Decision required before implementation — Q2: has `AD-008` been decided, and which branch?**

| Option | Consequence for this block |
|---|---|
| **(a)** **`ON_MODERATION` becomes durable** (auto-moderation defers to a human) | **All 62 defaulted sites become correct and need no change. The 62-site pass evaporates.** Only the default flip, the two doc corrections and the regression guard survive. Phase 05's validator was explicit that the "remove the durable state" branch must not be taken before `VAL-003` is resolved |
| **(b)** **The durable state is removed** | Every site that asserted the fabricated state must be retargeted onto a reachable state, and **each expectation change lands in the same commit as the production change that makes it necessary** (phase 07 VAL-003's rule). This is phase 05's territory, not a mechanical pass |
| **(c)** **Undecided** | **The 62-site pass does not start.** Doing it first risks ~62 edits of work that option (a) invalidates |

**The two-commit, each-green sequence (the report's "must land in one commit" is refuted):**

1. Add an explicit `status=` at the **62 defaulted** sites → **green** (behaviour identical;
   the default is still `ON_MODERATION`).
2. Flip **both** defaults to `AdStatus.PUBLISHED`, correct the two documents, add the
   self-verifying guard → **green** (the 62 now pass their explicit value; the 62 explicit
   sites are unaffected).

Nothing goes red at any point. **The report's "must not be split" is over-constrained**; the
genuine must-land-together constraint is the *expectation* rule from option (b) above.

**Binding constraints**

1. **This block may not start until Q1 and Q2 are both answered in writing.** Neither is the
   Implementor's to answer.
2. **The change to `src/backend/conftest.py` is `only` the `status` default** (and a
   docstring describing it). **No other fixture, no other parameter, no formatting.** The
   file has seven plans' "nobody" statements attached to it and one claimant.
3. **`_set_status_timestamp` must not change.** It has no `ON_MODERATION` branch, which is
   exactly why the default has never broken a `CheckConstraint`; the Implementor must
   understand why there is no `IntegrityError` in the failure output or they will chase a
   phantom.
4. **Both documentation files are corrected in the same commit as the flip.**
   `.kilo/rules/commands.md` documents the default as `AdStatus.PUBLISHED`; `docs/99-agent/rules.md`
   says to add `status=AdStatus.PUBLISHED` explicitly "if the test requires it". Both are
   misleading against `ON_MODERATION`, and project rule 14 requires them to move together.
5. **`src/telegram_bot/tests/conftest.py` is not edited** (C-9).
6. **A regression guard is added**: one test asserting `create_test_ad`'s default. That makes
   the documentation self-verifying and prevents a third drift. It is the cheapest item and
   the one that prevents recurrence.
7. **No production code is touched by this block.** If a failure reveals a production defect
   that is *not* `ON_MODERATION`-related, it is recorded and routed — not fixed here.
8. **`makemigrations --check` reports no changes** after both sub-commits.

**Implementor task**

```yaml
id: task_11_b14_create_test_ad_contract
title: "Add explicit status to the defaulted factory call sites, then flip the default and the docs (11-TEST-001)"
priority: high
depends_on: [task_11_b01_reconciliation_and_schedule]
source_reference: ".ai/plans/11-test-coverage-remediation.md"
source_section: "BLOCK 14 - The create_test_ad contract"
source_blocks: ["BLOCK 14"]
description: >
  create_test_ad and create_test_ads_bulk in src/backend/conftest.py default to
  AdStatus.ON_MODERATION, a durable state no production writer commits: submit_ad and
  ad_reactivate transition into it inside the same atomic() block that then calls
  auto_moderate, which has no third exit. 124 call sites in 22 files depend on that default
  (62 explicit, 62 defaulted). Add explicit status= at the 62 defaulted sites - behaviour
  preserving and green - then flip both defaults to PUBLISHED, correct .kilo/rules/commands.md
  and docs/99-agent/rules.md in the same commit, and add a regression guard asserting the
  default. Both sub-commits are green. The 62-site pass does not start until AD-008 is
  decided, and no step starts until conftest.py ownership is ruled.
goals:
  - "make the interesting variable explicit at every call site"
  - "flip both factory defaults and correct both documentation files in one commit"
  - "make the documentation self-verifying with one guard test"
  - "touch no production code, no other fixture and no other parameter"
files:
  - path: "src/backend/conftest.py"
    targets:
      - type: function
        name: create_test_ad
      - type: function
        name: create_test_ads_bulk
      - type: function
        name: _set_status_timestamp
    semantic_anchors:
      insert_before:
        type: function
        value: create_test_ads_bulk
  - path: ".kilo/rules/commands.md"
    targets:
      - type: section
        name: Project Commands
    semantic_anchors: {}
  - path: "docs/99-agent/rules.md"
    targets:
      - type: section
        name: Rules
    semantic_anchors: {}
  - path: "src/telegram_bot/tests/conftest.py"
    targets:
      - type: module
        name: conftest
    semantic_anchors: {}
changes:
  - action: modify_code
    description: >
      Sub-commit (a): add an explicit status= at each of the 62 defaulted call sites in the
      22 files of the re-measured census. Sub-commit (b): flip both factory defaults to
      AdStatus.PUBLISHED, update the docstring, correct both rule files in the same commit,
      and add the regression guard. _set_status_timestamp and
      src/telegram_bot/tests/conftest.py are read-only.
acceptance_criteria:
  - "every call site passes status= explicitly and the defaulted count is zero"
  - "both factory defaults are AdStatus.PUBLISHED and _set_status_timestamp is byte-identical"
  - "both documentation files state the shipped default and changed in the flip commit"
  - "the regression guard fails if the default is changed back"
  - "makemigrations --check reports no changes"
  - "src/telegram_bot/tests/conftest.py is unmodified and no production file was touched"
  - "the commit bodies name the Q1 option, the Q2 branch and the re-measured census"
```

---

### BLOCK 15 — Zero-coverage triage and the `moderation_fixtures.py` disposition

| | |
|---|---|
| **Findings owned** | the brief-derived zero-coverage surface; the phase-10-routed `CQ-002` / `CQ-004` disposition |
| **Class** | **reconciliation + coverage** |
| **Depends on** | BLOCK 1 |
| **Blocks** | BLOCK 8 (the `cabinet` hub disposition) |
| **Priority** | P3 |
| **Risk level** | **LOW** execution / **MEDIUM** judgement |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four** (this block is mostly a judgement, and judgements get all four) |

**Method caveat, and it governs the whole block.** The zero-coverage map is a **name-reference
analysis**: a production symbol is listed when its identifier never appears in any test
file's source text. It is a **screening tool**, not a coverage measurement, and it produces
false positives wherever a test reaches a symbol through the URLconf, a dispatcher or a
caller. The raw list is not a work list.

**The high-confidence items — and who actually owns each:**

| Module / symbol | Verdict | Owner |
|---|---|---|
| `apps/media/services/hash_service.py::FileHashService` | genuinely untested | **Phase 07** — the media dedup surface. **Not phase 11's** |
| `apps/search/services/category_fuzzy.py` (`get_active_category_names`, `_fuzzy_names_cache_key`) | genuinely untested | **Phase 08 BLOCK 10 + phase 10 BLOCK 15** — two phases are about to refactor it with no test to catch them. **Phase 11 does not write the test; it records the exposure** |
| `apps/media/services/filesystem.py::_record_deletion_error` | genuinely untested | **Phase 07 BLOCK 8** introduces `MediaDeletionError`'s "reader". The reader has no test. **Phase 07's** |
| `apps/moderation/views/queue.py` (all views) | genuinely unreferenced by name | **Phase 05 BLOCK 3** restores the human approval path whose *view* is unreferenced. **Phase 05's** |
| `apps/cabinet/views/hub.py` (`cabinet_hub`, `cabinet_settings`) | genuinely unreferenced; `test_cabinet_sections.py` covers a sibling view | **Nobody.** Phase 11's — two cheap behavioural tests through the URLconf |
| `src/backend/testing/moderation_fixtures.py` | **unused *and* not coverage-omitted** | **Nobody.** Double defect; Q10 |
| `apps/analytics/management/commands/show_metrics.py`, `apps/core/management/commands/profile_queries.py` | zero references | Management commands; `profile_queries` is the only production module importing `PerformanceSLO` with no test. **Routed, not tested** — a command's usefulness is measured by use |
| `src/backend/djlint_custom_rules.py`, `src/telegram_bot/services/ad_data/keyboards.py`, `feature_helpers.py` | zero references | **De-scoped** (§6) — tooling and presentational helpers |

**Confirmed false positives — do not write a test for any of these.** The name-reference
method flags them and they are covered: `AccountStateMiddleware._resolve_user` /
`._evaluate_user_state` (46 tests in 5 classes, including
`TestCrossPredicateAgreement`); `ads/views/listings.py::_suggest_category` and
`views/favorite.py::toggle_favorite` (reached by URL); `apps/core/utils/swr_cache.py`'s
private entry helpers (reached through `test_lookup_cache_swr.py`'s 27 tests);
`apps/search/services/alert_query.py`'s three private helpers (`test_alert_query.py` has 34
tests); `auto_moderation.py`'s seven private validators (`test_auto_moderation.py` has 29);
`apps/core/utils/cache.py`'s nine `*_cached_*` wrappers (reached through services); every
`AppConfig`; every `Command.add_arguments`; every `migrations/*.py` (coverage-`omit`ted).

**Decision required before implementation — Q10: `moderation_fixtures.py`.**

It is referenced by **nothing** in the test tree, and because it lives at
`src/backend/testing/` — not `tests/`, not `conftest.py`, not `test_*.py` — it **escapes all
seven coverage-`omit` patterns** and is measured as production code. It is simultaneously
unused test scaffolding and a coverage-denominator item.

| Option | Consequences |
|---|---|
| **(a)** | **Adopt it** as the home for a moderation fixture, and wire it into `src/backend/conftest.py` — which means it lands behind **Q1**'s blocker and lands on the most contended file. **Gains:** it may be the intended home for a fixture nobody wired up. **Costs: it drags BLOCK 15 into BLOCK 14's blocker** |
| **(b)** | **Delete it.** **Gains:** removes a dead module and a coverage-denominator item. **Costs: the dead-code policy says *investigate its purpose before proposing removal***, and this module has a plausible second life. If the purpose turns out to be valid, deletion destroys the intent |
| **(c)** | **Move it under a path the omit patterns cover** (e.g. `src/backend/testing/tests/…` or give it a `conftest`-adjacent name) so it stops being measured as production code, and record the adoption question separately | **Gains:** fixes the *coverage* half of the defect without deciding the *adoption* half. **Costs:** a rename that a later adoption may make pointless |

**Decision required before implementation — Q11: phase 10's two routed AST rules.** Phase 10
routes `CQ-002` and `CQ-004` here with the reasoning *"a rule that must first be made true
cannot be enforced before it is true"*, and both would false-positive on ~26 legitimate
`AppConfig.ready()` deferrals and on the `request.POST` + `save()` delegate in
`moderation/views/review.py`. **Phase 10's refusal is upheld and recorded** (§6). The
Implementor may not adopt them, and may not build them "with an exclusion list".

**Binding constraints**

1. **No test is written for a symbol another phase owns.** The table above is the ownership
   decision; writing one anyway duplicates work and creates two tests to keep in step.
2. **The `cabinet/views/hub.py` tests go through the URLconf**, not by calling the view
   function — otherwise they are a unit test of an unreached function, which is what the
   name-reference map already got wrong once.
3. **`src/backend/conftest.py` is not edited** unless Q10 option (a) is chosen *and* Q1 is
   answered. Neither is a default.
4. **A command with no test is not automatically a defect.** `show_metrics` and
   `profile_queries` are routed, not tested.
5. **The disposition table is the deliverable.** A block that tests two views and writes no
   disposition for the other eight items is incomplete.

**Implementor task**

```yaml
id: task_11_b15_zero_coverage_triage
title: "Triage the zero-coverage surface, add the cabinet hub tests, disposition moderation_fixtures (11-TEST-adjacent)"
priority: low
depends_on: [task_11_b01_reconciliation_and_schedule]
source_reference: ".ai/plans/11-test-coverage-remediation.md"
source_section: "BLOCK 15 - Zero-coverage triage and the moderation_fixtures.py disposition"
source_blocks: ["BLOCK 15"]
description: >
  The name-reference map is a screening tool with known false positives; do not build a plan
  from the raw list. For each high-confidence item record an owner: FileHashService, _record_
  deletion_error and the moderation queue view belong to phases 07 and 05; category_fuzzy is
  being refactored by phases 08 and 10 with no test. apps/cabinet/views/hub.py has no owner and
  gets two URLconf-level tests. src/backend/testing/moderation_fixtures.py is unused and escapes
  all seven coverage-omit patterns; apply the Q10 option after investigating its purpose.
  Uphold phase 10's refusal of the two routed AST architecture rules.
goals:
  - "give every high-confidence zero-coverage item an owner or a test"
  - "write no test for a symbol another phase owns and no test for a confirmed false positive"
  - "resolve moderation_fixtures.py under the Q10 option"
files:
  - path: "src/backend/apps/cabinet/tests/test_cabinet_sections.py"
    targets:
      - type: module
        name: test_cabinet_sections
  - path: "src/backend/apps/cabinet/views/hub.py"
    targets:
      - type: function
        name: cabinet_hub
      - type: function
        name: cabinet_settings
    semantic_anchors: {}
  - path: "src/backend/testing/moderation_fixtures.py"
    targets:
      - type: module
        name: moderation_fixtures
changes:
  - action: add_code
    description: >
      Add the cabinet hub tests through the URLconf and apply the Q10 option to
      moderation_fixtures.py. Commit the per-item disposition table. Do not add any test for a
      symbol another phase owns.
acceptance_criteria:
  - "every high-confidence zero-coverage item has a recorded owner, a test or a stated rationale"
  - "the cabinet hub tests request the URLs rather than calling the view functions"
  - "no test was written for a confirmed false positive or for a phase-owned symbol"
  - "moderation_fixtures.py is either adopted per Q10(a) or deleted with its purpose investigated first"
  - "the two AST architecture rules routed from phase 10 were not built"
  - "src/backend/conftest.py is unmodified unless Q10(a) was chosen and Q1 answered"
```

---

### BLOCK 16 — Correct the audit handbook and close out the CI-scope item

| | |
|---|---|
| **Findings owned** | `11-TEST-013` item 2 (the residual, post-closure) and the report's advisory 2 |
| **Class** | **configuration + documentation** |
| **Depends on** | **BLOCK 2** — the handbook's claim is only *false* once BLOCK 2 has landed |
| **Priority** | P3 |
| **Risk level** | **LOW** |
| **Required agents** | **Auditor · Planner.** Validator only if Q12's answer shows phase 01 has **not** already done the CI-scope item |

**What is documented wrong.** `.kilo/commands/audit/phases/11-audit-test-coverage.md` asserts
the suite has an **"80 % branch coverage gate"** and that bot tests use `transaction=True` in
**"9 files"**. Both are false on the evidence already in hand: CI has **no** coverage gate
(`fail_under` is inert because the config never loads — C-3), and the figure is **48 scopes in
39 files** (bot: 24). The handbook's coverage assertion is the clearest single statement of the
**belief gap** `11-TEST-002` identifies — a future audit run will read it and inherit the
false premise.

**Why it must follow BLOCK 2.** Correcting "there is no 80 % branch coverage gate" in the same
week that a block turns one on would be two contradictory statements about the same system in
two commits. The correction describes the state *after* BLOCK 2; therefore it lands after.

**The residual CI-scope item (Q12).** The report's item 2 — add a `basedpyright .` step for
`src/telegram_bot` and move `ruff` to the repo root — survives independently of the finding's
closure, because the gate is green in **both** scopes today and widening the scope is
near-zero cost. **But phase 01's `ENT-004` block was exactly "CI lint/typecheck scope to
`src/`" and was executed** (`8bf0517`). Before writing anything here, the Auditor must read
phase 01's plan and its execution record. **If phase 01 already did it, this block is
documentation only.** Block 1's Q12 answer settles it.

**Binding constraints**

1. **The handbook is an audit *input*, not a finding.** It is corrected as documentation; no
   `11-TEST-` finding is raised against it.
2. **Only the two false claims are touched.** The handbook's remaining content is not this
   plan's review surface.
3. **No existing `.ai/audit/**` file is edited.** The handbook lives under
   `.kilo/commands/audit/phases/`, which is agent tooling, not an audit phase artefact.
   `git status --short .ai` must show no new modifications.
4. **No new `11-TEST-` marker is written** into any shipped source file.
5. **No CI step is edited unless Q12 says phase 01 has not already done it**, and if it is
   edited, the change is the narrowest possible — one working directory and one added step.

**Implementor task**

```yaml
id: task_11_b16_handbook_and_ci_scope
title: "Correct the phase-11 audit handbook and close the CI lint/typecheck scope item (11-TEST-013 item 2)"
priority: low
depends_on: [task_11_b02_ci_coverage_config]
source_reference: ".ai/plans/11-test-coverage-remediation.md"
source_section: "BLOCK 16 - Correct the audit handbook and close out the CI-scope item"
source_blocks: ["BLOCK 16"]
description: >
  The phase-11 audit handbook asserts an "80 % branch coverage gate" that CI does not have -
  fail_under is inert because coverage.py reads config from the CWD only and the pytest step
  runs from src/backend - and claims bot tests use transaction=True in "9 files" when it is 48
  scopes in 39 files. Correct both claims after BLOCK 2 has landed. Separately, close out
  11-TEST-013's item 2 (a basedpyright step for src/telegram_bot and ruff at the repo root)
  only if phase 01's ENT-004 block did not already ship it.
goals:
  - "stop a future audit run from inheriting the false coverage-gate premise"
  - "edit a CI step only if phase 01 has not already widened the lint/typecheck scope"
files:
  - path: ".kilo/commands/audit/phases/11-audit-test-coverage.md"
    targets:
      - type: section
        name: Coverage
    semantic_anchors: {}
  - path: ".github/workflows/ci.yml"
    targets:
      - type: job
        name: typecheck
    semantic_anchors: {}
changes:
  - action: modify_code
    description: >
      Correct the two false claims in the handbook. Edit the CI workflow only under the Q12
      outcome where phase 01 did not already ship the wider lint/typecheck scope.
acceptance_criteria:
  - "the handbook no longer asserts an 80 % branch coverage gate"
  - "the handbook no longer claims 9 files for bot transaction=True scopes"
  - "the handbook states the state that exists after BLOCK 2, not before it"
  - "git status --short .ai shows no new modifications"
  - "no CI step was edited unless Q12 showed phase 01 had not already widened the scope"
  - "no 11-TEST- marker was written into any shipped source file"
```

---

## 4. Dependency graph

### 4.1 The ordered test-change schedule — this is the deliverable

**Every contested test file gets exactly one owning phase, one phase-11 block, and one
ordering rule.** Other phases' plans are checked against this table; if a plan disagrees,
**this table wins and the disagreement is escalated to the coordinator**, because the
alternative is two agents editing one file believing the other is not.

| # | Test file | Owning phase | Phase-11 block | Ordering rule |
|---|---|---|---|---|
| 1 | **`src/backend/conftest.py`** | **05** BLOCK 4 claims · 03 "must not edit it at all" · 04, 06, 07, 08, 09, 10 "nobody" | **14** | **Q1 GATED — coordinator decides whether 14 or 05 BLOCK 4 owns it.** Then Q2 (AD-008 branch) decides whether 14's 62-site pass is work or a no-op. **Nothing in BLOCK 14 starts before both are written down** |
| 2 | `apps/search/tests/test_search_view.py` (10 phase-08 blocks + 1 phase-10 block) | **08** BLOCK 3, then **10** BLOCK 14 | **9** | **`08 BLOCK 3 → 10 BLOCK 14 → 11 BLOCK 9`.** A block that misses its turn must re-read the file *and* both plans immediately before editing, and stop-and-report on uncommitted changes |
| 3 | `apps/search/tests/test_search_query_count.py`, `test_search_slo.py` | **08** BLOCKs 1/3/11 · **10** BLOCKs 14/15 | **none** | Phase 11 never edits either. They are the tripwires detecting whether BLOCKs 5 and 6 moved a query count or a wall-clock gate. `test_search_slo.py` is CI's separately-named gate |
| 4 | `apps/core/tests/test_advisory_lock_ids.py` (6 phases) | whichever phase **allocates** `AdvisoryLockId` | **none** | Phase 11 allocates none and edits nothing here. Three files, one commit, coordinator told first — phase 07 BLOCK 8 and phase 06 BLOCK 15 are the live claimants |
| 5 | `apps/core/tests/test_ad_image_delete_signal.py` + `test_delete_photo_single_call.py` | **07** BLOCKs 1/2/11 (MEDIA-001) · **03** BLOCK 1 · **05** BLOCK 13 | **7** | **`11 BLOCK 7's scaffold lands BEFORE or WITH phase 07's MEDIA-001`** (Q7' (a) or (b); (c) is the option the finding exists to prevent). Phase 07 may not start its refcount work before the scaffold |
| 6 | `apps/core/tests/test_advisory_lock_release_log.py` | **03** BLOCK 2 | **none** | Phase 03 owns lifting the `on_commit` patch-out ban and rewriting those two tests. Phase 11 records the reservation and does not touch the file |
| 7 | `apps/moderation/tests/test_approve_ad_side_effects.py` (5 phases) | **05** BLOCK 3 · **06** BLOCK 7 · **09** BLOCKs 6/7/14 · **10** BLOCK 11 | **7** | **`11 BLOCK 7 → 05 BLOCK 3`.** BLOCK 7 replaces the two patched `on_commit` sites with real execution; phase 05's retargeting then reads the real-execution version |
| 8 | `apps/core/tests/test_support_admin.py` | **06** BLOCKs 12/13 | **8** | **`06 → 11 BLOCK 8`.** Phase 06's VAL-007 scoping input lands first. Phase 11 extends, never rewrites |
| 9 | `apps/search/tests/test_autocomplete.py` | **08** BLOCK 5 | **10** | **`08 BLOCK 5 → 11 BLOCK 10`.** The introspection test cannot pass until the `UniqueConstraint` and its migration land |
| 10 | `apps/core/tests/test_migrations.py` + `config/settings/test_migrations.py` | **02** BLOCKs 3/4/5/9 | **13** | **`02 → 11 BLOCK 13`.** Phase 13 extends the subprocess shape; it does not rewrite phase 02's applicability and idempotency tests |
| 11 | `apps/moderation/tests/test_admin_actions.py` (14 explicit `ON_MODERATION` sites, 5 `getsource`, 3 `transaction=True` scopes) | **05** BLOCK 3 · **03** · **10** BLOCK 12 · **01** BLOCK 1 | **14 (read/write, one site)** | Phase 11 touches exactly one `ON_MODERATION` site in BLOCK 14's pass. **No other phase-11 block opens this file** |
| 12 | `apps/ads/tests/test_edit_views_locking.py` (7 `getsource`, 8 former type errors) | **10** BLOCK 16 · **03** BLOCK 5 · **01** | **11 (rule only)** | Phase 11 writes the `getsource` **rule** and does not edit the file unless Q8(b) selects an assertion in it. Phase 10's BLOCK 16 is the change that would break those 7 tests |
| 13 | `apps/telegram_bot/tests/test_unsubscribe.py` (2 `getsource`, `xdist_group("bot_concurrent")`) | **03** · **10** BLOCKs 10/11 | **11 (rule only)** | Same as row 12. The two order assertions are named as *must survive* in the rule |
| 14 | `apps/core/tests/test_migrate_locked.py` (4 `getsource`; `TestSessionLockLogging` is a shipped phase-01 guard) | **01** · **02** · **03** BLOCK 2 · **09** BLOCK 5 | **11 (rule only)** | `TestSessionLockLogging` is the counter-example in the rule — a source-text test that **earns** its place |
| 15 | `apps/core/tests/test_i18n_completeness.py` (8 phases name it) | all phases as a **gate** | **none** | Phase 11 does not edit it. It is a tripwire for every block |
| 16 | `apps/ads/tests/test_features_filter.py` (3 requests, max 2 slugs; AND-semantics) | **08** BLOCK 1 (must stay green unchanged) | **6 (read-only unless Q6 chooses it)** | Under Q6 this file is the alternative home. Its existing AND-semantics cases are the **positive control** for BLOCK 6 and must stay green |
| 17 | `apps/moderation/tests/test_priority.py` / `test_priority_service.py` (**51 of the 62 defaulted sites**) | **10** BLOCK 9 · **03** BLOCK 3 · **05** Q10 | **14 (mechanical only)** | Phase 11's only change is an explicit `status=`. It changes no assertion and no expectation. Phase 10's BLOCK 9 and phase 05's triage are unaffected |
| 18 | `src/backend/tests/test_docs_ci_parity.py`, `apps/core/tests/test_ci_security.py` | **05**/`01`/CI owners | **none** | Phase 11 reads them for the workflow-claim baseline and edits neither |

**Where two phases both need a file, the rule is: serialise them, and the block that runs
second re-reads the first's plan immediately before editing.** The second half matters as
much as the first — six plans are open and each names blocks that may or may not have run.

### 4.2 The safe serial order

One Implementor, strictly sequential, one commit per block (§1.4). The numbering *is* the
order.

| # | Block | Findings | Class | Depends on (in-plan) | External gate | Risk |
|---|---|---|---|---|---|---|
| 1 | Reconciliation + schedule | `VAL-001`, `VAL-002`, `TEST-013`, `TEST-001` count | R | — | — | **LOW** |
| 2 | CI coverage config | `TEST-002` | C | 1 | **Q2** | **HIGH** |
| 3 | Hang bounds | `TEST-009` | C | 1 | **Q4** | MED |
| 4 | Seed recoverable | `TEST-008` | C | 1 | **Q5** | LOW |
| 5 | Test statement timeout | `TEST-003.1` | C | 1, 3 | **Q3** · phase 03 `DB-002` + `DB-004` | **HIGH** |
| 6 | `?features=` bound test | `TEST-003.2` | V | 1, 5 | **Q6** · phase 08 BLOCK 1 | MED–HIGH |
| 7 | `on_commit` scaffold + rollback | `TEST-014`, `TEST-004` | V | 1 | **Q7'** · phase 07 `MEDIA-001` | **HIGH** |
| 8 | Admin form contract | `TEST-012` | V | 15 | **Q7** · phase 06 `VAL-007` | MED |
| 9 | `?q=` hostile corpus | `TEST-006` | V | 1 | phase 08 BLOCK 3 | MED |
| 10 | Dedup coverage | `TEST-007` | V | 1 | **Q7''** · phase 08 BLOCK 5 | MED |
| 11 | `getsource` rule | `TEST-010` | V/R | 8 | **Q8** | MED |
| 12 | Cross-process assertions | `TEST-005` | V | 1 | **Q8'** · phase 04 · phase 06 | MED |
| 13 | Migration effect tests | `TEST-011` | V | 1 | **Q9** · phase 02 | MED |
| 14 | `create_test_ad` contract | `TEST-001` | V | 1 | **Q1 + Q2 — BLOCKERS** | **HIGH** |
| 15 | Zero-coverage triage | brief-derived | R/V | 1 | **Q10**, **Q11** | LOW/MED |
| 16 | Handbook + CI scope | `TEST-013` item 2, advisory 2 | C/D | 2 | **Q12** | LOW |

`R` = reconciliation · `C` = configuration · `V` = coverage · `D` = documentation.

### 4.3 The DAG and why each edge exists

```
  [1 reconciliation] ──┬──▶ [2 CI coverage] ──▶ [16 handbook + CI scope]
                        ├──▶ [3 hang bounds] ──▶ [5 test timeout] ──▶ [6 ?features=]
                        ├──▶ [4 seed]
                        ├──▶ [7 on_commit scaffold]      <── phase 07 MEDIA-001 (before/with)
                        ├──▶ [9 ?q= corpus]               <── phase 08 BLOCK 3 (with)
                        ├──▶ [10 dedup]                   <── phase 08 BLOCK 5 (with)
                        ├──▶ [12 cross-process]           <── phase 04 / phase 06 predicates
                        ├──▶ [13 migration effect]        <── phase 02
                        ├──▶ [14 create_test_ad]          <── Q1 + Q2 BLOCKERS
                        └──▶ [15 zero-coverage] ──▶ [8 admin form] ──▶ [11 getsource rule]
```

| Edge | Kind | Why it exists |
|---|---|---|
| **1 → everything** | hard, process | BLOCK 1 produces the ownership map and the schedule (§4.1). Every other block's ordering against another phase is an *input* to that block, and six plans are open. A block that starts before BLOCK 1 has no way to know whether the file it is about to edit has an owner |
| **1 → 2** | hard, process | BLOCK 2 is the only block whose edit the handbook's false claim is about; BLOCK 16's correction must describe the post-BLOCK-2 state |
| **3 → 5** | hard, mechanism | BLOCK 5 adds a **second** time bound to the same harness. The implementor must know what `pytest-timeout` already does before adding a PostgreSQL-level bound, or the two interact invisibly (a `thread`-method timeout that returns while the statement keeps running defeats BLOCK 5's entire purpose — Q4 option (c)) |
| **5 → 6** | hard, prerequisite | BLOCK 6's test provokes a slow query. **Running it without BLOCK 5's bound risks the shared instance** — which is very likely why the test was never written. Phase 08's probe terminated the cluster twice |
| **2 → 16** | hard, correctness | The handbook says "there is an 80 % branch coverage gate". BLOCK 2 makes that true. Correcting it before BLOCK 2 lands asserts a false statement about a system that is about to change; correcting it after is a description of reality. **Content dependency, not preference** |
| **15 → 8** | hard, scope | BLOCK 15 decides whether `cabinet/views/hub.py` and `moderation_fixtures.py` get tests or a disposition, and BLOCK 8 adds a second URLconf-level admin/cabinet surface test in the same run. Two blocks writing cabinet-level tests in one review is one block too many |
| **8 → 11** | hard, mechanism | BLOCK 11's rule is *about* what BLOCK 8's generated-form contract replaces. `test_admin_pii_containment.py`'s four substring assertions are deleted **because** BLOCK 8 covers the admin surface by a stronger mechanism. Reversed, the deletion happens with nothing behind it |
| **7, 9, 10, 12, 13 → 1** | external, hard | Each is a same-commit-with-production-change rule (phase 07 VAL-003) against a named phase-08/07/04/06/02 block. These are not in-plan edges; the coordinator sequences them (§5) |
| **14 → 1** | external, hard | Q1 and Q2 are coordinator and phase-05 decisions. **BLOCK 14 is the only block in this plan that cannot start on its own**, and that is correct: seven plans forbid `src/backend/conftest.py` and one claims it |

### 4.4 Where there is deliberately **no** edge, and why

| Pair with no edge | Why |
|---|---|
| **2 ↔ 3 ↔ 4** | Three independent configuration changes with three independent gates and three independent failure modes (a gate that starts failing, a ceiling that is too low, a plugin whose detection is disabled). Coupling them would put Q2, Q4 and Q5 in one commit, so a reviewer approving one is approving all three, and reverting one reverts all three. They share `ci.yml` and nothing else — one commit each, one re-read each |
| **7 ↔ 8 ↔ 9 ↔ 10 ↔ 12 ↔ 13** | Six different files, six different owning phases, six different gates. With one Implementor they run in series anyway; an artificial edge would only add a reason to defer a block that nothing actually blocks |
| **13 ↔ 5** | A migration-effect test needs a database and a statement bound; it does not need *this* bound, because the repro database is not the shared `test_mko_bazuna`. A real edge here would be a coincidence, not a constraint |
| **14 ↔ 5** | Different systems (Python fixture default vs PostgreSQL connection option) and different files. The only interaction is that both are "global changes to the whole suite" — which is an argument for reviewing them, not for ordering them |
| **15 ↔ 14** | BLOCK 15 *may* be forced behind BLOCK 14 by **Q10 option (a)** — but that is a **gate consequence, not a scheduling rule**, and it is recorded as such. Under options (b) or (c) the two are fully independent |
| **16 ↔ everything but 2** | Documentation about the audit handbook. It only becomes true after BLOCK 2 and is false before |
| **Any block ↔ another phase** | Not an in-plan edge. §5 records the ordering from phase 11's side; **the coordinator sequences the cross-phase gates.** Phase 11 does not contact, negotiate with, or wait on any other agent |

### 4.5 The orders that are unsafe

1. **BLOCK 6 before BLOCK 5.** The hostile-`?features=` test provokes a query that, unbounded,
   can take the shared PostgreSQL instance offline for **22 databases** including 17 xdist
   worker databases. This is not hypothetical: phase 08's probe did exactly that, twice.
2. **BLOCK 5 before phase 03's `DB-002`.** `record_event` currently swallows the
   `OperationalError` a statement timeout raises. Bounding first converts a swallowed error
   into a new failure mode in the analytics path. **Phase 03 recorded this; it is a live
   hazard.**
3. **BLOCK 2 fixing only `ci.yml`.** The nightly workflow carries the identical bare `--cov`
   and the same `working-directory`, and the report never mentions it. A one-file fix leaves
   the nightly measuring the same inert configuration and looks complete.
4. **BLOCK 2 landing without Q2's measurement.** The edit is one line; the effect is that a
   gate which has never fired begins firing. Landing it unmeasured converts a MEDIUM finding
   into a red CI on arrival with no way to tell whether the coverage is genuinely below 80 %
   or the measurement is newly counting branch coverage.
5. **BLOCK 14 before Q1 or Q2.** Seven plans forbid `src/backend/conftest.py` and one claims
   it. And under the "make `ON_MODERATION` durable" branch of AD-008 the 62-site pass is
   **work that does not need doing** — doing it first risks ~62 edits that a product decision
   invalidates.
6. **BLOCK 14's two sub-commits merged, or reversed.** The mechanical pass first, the default
   flip second. Reversed, the flip turns 62 silent inheritances into loud failures with no
   triage map.
7. **BLOCK 7's scaffold after phase 07's `MEDIA-001`.** A refcount check inside an `on_commit`
   callback verified by 7 tests in 2 files, with eight transactional media test files
   invisible to it. That is phase 07 VAL-004's half-fix hazard approached from the test side.
8. **BLOCK 8 or 9 or 10 landing without their production change.** Three test-expectation
   changes whose production fixes are phase 08 BLOCKs 3 and 5. Phase 07 VAL-003's rule: *a
   test-expectation change lands in the same commit as the production change it follows from.*
9. **BLOCK 11 deleting all 27 `getsource` assertions.** It removes
   `test_migrate_locked.py::TestSessionLockLogging`, a shipped phase-01 hard regression guard,
   and two lock-order assertions in `test_unsubscribe.py`, from files five other phases hold.
10. **Any block deleting a test to make another phase's change green.** The standing failure
    mode of this finding class. Project rule 3: production code is king — if a test conflicts
    with architecture or business logic, fix or remove the **test**, never distort production
    code — and a test that exists only to mirror an implementation is removed **on its own
    merits** under BLOCK 11's written rule, never as a side effect of someone else's change.
11. **Any block restoring `.ai/audit/11-test-coverage/findings.md`.** It is deleted; the
    validated report preserves the corrected evidence inline.
12. **Any block running the suite on the host.** There is no PostgreSQL on `localhost:5432`.

### 4.6 What the DAG does *not* decide

The DAG orders blocks. It does **not** resolve Q1 … Q12. Each is a gate inside a block,
recorded in that block's `extra_context` and in §0.5, and §8.1 checks that a **written** answer
exists for each. **A block whose gate is unanswered does not start, and the Implementor is
forbidden from choosing the option.**

The DAG also does not sequence phase 11 against the other phases. §5 does, from phase 11's
side only.

---

## 5. Cross-phase coordination

Plans `.ai/plans/01-…` through `.ai/plans/10-code-quality-remediation.md` exist. **Phases
12–15 are being planned in parallel right now.** `.ai/plans/12-production-ops-remediation.md`
was **absent when this plan was written and appeared while it was being written** — the
concurrent-agent drift the anchor rule exists for, observed and recorded rather than papered
over. Phase 12's §5 was **not read**; §8.2 carries the instruction to read it and extend §5.4
before phase 12's first block. **Phase 11 does not contact any other agent.** This section is
a one-directional boundary contract: what phase 11 owns, what it will not touch, and where
its boundaries lie.

**The convention every other plan adopted independently (phases 03, 05, 06, 07, 08, 09, 10):**
a behaviour change's *incidental* test rewrite belongs to the phase making the behaviour
change, and is **explicitly denied to phase 11** in each plan's §5. Every one of those plans
says, in terms, *"Phase 11 must not claim them, and phase N must not expand them into new
coverage while rewriting them."* **This plan does not overturn that.** The schedule in §4.1
is a **serialisation aid**, not a re-assignment.

### 5.1 Hot spot 1 — `src/backend/conftest.py` ★ the blocker

| Phase | Claim | Source | Phase 11's position |
|---|---|---|---|
| **01** | read-only | §6 | respect |
| **02** | "`_run_in_subprocess` consolidation routed to phase 10 / **phase 11**" | §5.2, §6 | see §5.4 item 6 |
| **03** | "**must not edit it at all** — the most contended file in the repository" | §5.3 | respect absolutely |
| **04** | "No … fixture reshaping, no conftest redesign" unless BLOCK 4 option B requires it | §6.2.8 | respect |
| **05** | "**BLOCK 4** — the *one* justified exception in this plan … the change must be **only** the `status` default" | §5.3 | **competing claim — Q1** |
| **06**, **07**, **08**, **09**, **10** | "**Nobody in this plan**" | §5.3 | respect |
| **11** | `11-TEST-001` steps 2–4 need the `status` default **and** both doc files | this plan | **competing claim — Q1** |

**The rule.** This is a direct, unresolved collision and it is a **blocker**, not a
preference. **Phase 05 BLOCK 4 and phase 11 BLOCK 14 want the same one-line change to the same
file.** Three options, in BLOCK 14: (a) fold into phase 05 BLOCK 4 and record `11-TEST-001`
as *closed by phase 05*; (b) carve out as a phase-11 exception, sequenced after AD-008;
(c) defer. **The coordinator decides.** Phase 11's recommendation, offered as a
recommendation and not as a choice: **(a)**, because phase 05 has already filed the claim,
already written the triage rule, already written the mandatory internal order and already
written the census pre-step for exactly this change — re-filing it under a second phase ID
duplicates all of that and splits the census across two records.

**Two corrections phase 11 makes to phase 05's BLOCK 4, which must be applied whichever option
wins:**

1. **C-9 — the bot conftest does *not* redefine the factories.** Phase 05's finding 1 says it
   does and makes "both conftests must change together" a hard requirement. The bot conftest's
   own docstring says the opposite. **One default change in `src/backend/conftest.py` reaches
   both trees.** Acting on phase 05's claim edits a file that does not need editing, on the
   most contended file in the repository.
2. **C-1 — the census is 124 sites in 22 files, not 34 or 111.** Phase 05's BLOCK 4 already
   anticipated that its count was a floor ("the number must be re-measured, not inherited").
   The re-measured figure at `6413df5` is **124 / 22**, of which **62 are defaulted** — the
   subset the mechanical pass actually touches, stable across both anchors.

### 5.2 Hot spot 2 — the search test cluster (`test_search_view.py` + the two tripwire files)

| Owner | Block | What it owns | Ordering rule |
|---|---|---|---|
| **08** | BLOCK 1, 3, 4, 5, 6, 7, 9, 10, 11, 12 | ten blocks in `test_search_view.py`; the NUL fix; the `UniqueConstraint` | **First** in the file |
| **10** | BLOCK 14 | the `build_listings_context()` extraction; `test_search_query_count.py` and `test_search_slo.py` are its tripwires | **Second** |
| **11** | **BLOCK 9** | the C0/NUL corpus, in phase 08 BLOCK 3's commit | **Third** |
| **11** | **BLOCK 6** (read-only under Q6) | the alternative home for the hostile-`?features=` test | with phase 08 BLOCK 1 |
| **11** | **BLOCK 10** | dedup coverage in `test_autocomplete.py` | after phase 08 BLOCK 5 |

**The rule:** `08 BLOCK 3 → 10 BLOCK 14 → 11 BLOCK 9`, and `08 BLOCK 5 → 11 BLOCK 10`.
A block that misses its turn **must re-read the file and both other plans immediately before
editing**, and must stop and report on uncommitted changes. **`test_search_query_count.py`
(`_QUERY_BOUND = 100`, whose own comment records the bound was loosened and "should be
tightened") and `test_search_slo.py` (`SEARCH_SLO_MS == 2000`, CI's separately-named gate)
are edited by no phase-11 block.** They are how BLOCKs 5 and 6 are *detected*.

### 5.3 Hot spot 3 — the media `on_commit` surface

| Owner | Block | What it owns | Ordering rule |
|---|---|---|---|
| **03** | BLOCK 1 | `test_ad_image_delete_signal.py` in the sweep suites | any |
| **05** | BLOCK 13 | `test_ad_image_delete_signal.py` | any |
| **07** | BLOCKs 1, 2, 11 | `MEDIA-001` — the reference check **inside** the `on_commit` callback; its own VAL-003 names the three tests that break | **After 11 BLOCK 7's scaffold** |
| **11** | **BLOCK 7** | the `transaction=True` scaffold and the rollback-negative tests | **Before or with 07** |

**The rule:** `11 BLOCK 7 → 07 MEDIA-001` (Q7' (a) or (b); option (c) — after — is the option
the finding exists to prevent). Phase 07's VAL-003 already found the three
`test_ad_image_delete_signal.py` tests that will break; **phase 11 supplies the reason phase
07 could not state from inside its own layer** — they are the only tests in that file under
`transaction=True`, and the media surface as a whole is **2 files / 7 tests** (C-4), not a
sweep surface. Phase 07 additionally did not know that `test_delete_photo_single_call.py`'s 4
tests also run the callback.

**`apps/core/tests/test_advisory_lock_release_log.py` is phase 03 BLOCK 2's** — "BLOCK 2 is
where that ban is lifted … it must rewrite the two tests". Phase 11 records the reservation
and does not touch the file.

### 5.4 What phase 11 must **not** do, for other phases' sake

| Other phase | What phase 11 must not do | Boundary |
|---|---|---|
| **Phase 01** | Must not re-file a red-typecheck remediation; must not re-litigate `ENT-004` | `11-TEST-013` is **closed** (C-2). Phase 01's `ENT-004` block already shipped the lint/typecheck scope (`8bf0517`) — Q12 checks it before BLOCK 16 writes anything |
| **Phase 02** | Must not edit `config/settings/base.py`, `production.py`, `dev.py`, `local.py`, `.env*`, or `secret_validation.py`; must not allocate a lock id; must not consolidate the `_run_in_subprocess` helpers | BLOCK 5 touches `config/settings/test.py` **only**. Phase 02 routed the subprocess-helper consolidation to "phase 10 / phase 11"; **phase 11 declines it** (§6) — the consolidation is not a test-coverage finding and phase 02's own BLOCKs own it |
| **Phase 03** | Must not edit `src/backend/conftest.py`; must not add a production `statement_timeout`/`lock_timeout`; must not take an `AdvisoryLockId`; must not open `test_advisory_lock_release_log.py`; must not start the BLOCK 11-style legacy sweep | BLOCK 5 is the **test-side** bound only and is hard-blocked on `DB-002` — `record_event` swallows the resulting `OperationalError` until then |
| **Phase 04** | Must not reshape fixtures or redesign conftests; must not add a fixture for BLOCK 12 | Every phase-11 fixture question is resolved **against** adding one: BLOCK 4 uses an artifact upload, BLOCK 5 uses a settings option, BLOCK 12 reuses `sync_to_async` |
| **Phase 05** | Must not touch `Ad.transition_to`, `ALLOWED_TRANSITIONS`, `search_vector*`, the FTS trigger, or `setup_search_triggers`; must not start the 62-site pass before `AD-008` is decided; must not retarget a producer test | BLOCK 14 is a **mechanical** pass and an expectation-free flip. Under Q2(b) the *retargeting* is phase 05's, and each retargeted expectation lands with the production change |
| **Phase 06** | Must not expand a required test rewrite into new coverage; must not add a blanket admin data-subject rule | `VAL-007` is **mandatory** on BLOCK 8. `test_support_admin.py` already asserts on `SupportContactAdmin.telegram_id`, and a blanket rule false-positives on a support *channel* id |
| **Phase 07** | Must not touch the media pipeline, `MEDIA_ROOT` staging, thumbnail generation or `sweep_orphaned_media`; must not add a reference check to `media/signals.py` | BLOCK 7 adds tests only. `apps/media/tests/test_sweep_orphaned_media.py` is transactional and **stays** transactional — marking it `transaction=True` so the scaffold would pass is a change to another phase's test |
| **Phase 08** | Must not cap `feature_slugs`, must not add a `max_length` or validator to `ListingsQueryParams`, must not add the `PopularSearch` `UniqueConstraint`, must not change the join loop | BLOCK 6 is the *test*; phase 08 BLOCK 1 is the *cap*. BLOCK 10 asserts a constraint phase 08 BLOCK 5 creates. `test_features_filter.py` stays green unchanged |
| **Phase 09** | Must not add a rate limiter, must not change `classify_contact_deep_link`, must not touch `api_bulk.py`, must not write a non-bandit-clean `subprocess.run` call | Phase 02 routed `VAL-006` (the `bandit` path) to phases 12/10, **not** 11. Note the interaction: fixing it newly scans the whole repository, so **any subprocess invocation BLOCK 13 adds must be list-form and must not contain a literal temp path** |
| **Phase 10** | Must not build the two AST architecture rules it routed here (`CQ-002`, `CQ-004`) | Phase 10's own reasoning is *"a rule that must first be made true cannot be enforced before it is true"*; both would false-positive on ~26 legitimate `AppConfig.ready()` deferrals and on the `request.POST` + `save()` delegate in `moderation/views/review.py`. **Upheld and recorded** (§6). **Its rule on test rewrites — "must not expand a required test rewrite into new coverage" — is a constraint on phase 10 that phase 11 respects in reverse: phase 11 does not rewrite its tests either** |
| **Phase 12** | Must not write a runbook or change deployment configuration | **`.ai/plans/12-production-ops-remediation.md` appeared while this plan was being written and was not read.** BLOCKS 2, 3, 4 and 16 touch `.github/workflows/**` only — CI, not deployment — but that distinction must be confirmed against phase 12's own §5 before its first block (§8.2) |
| **Phase 13** | Must not make a latency or index claim, and must not `EXPLAIN` anything | BLOCK 3's timeout value and BLOCK 9's corpus are chosen against `TestSearchResponseSLORegression`'s `SEARCH_SLO_MS == 2000`, which is a **tripwire, not a measurement to grade** |
| **Phase 14** | Must not regenerate locale files | **No block in this plan adds a string.** `locale/**` is untouched by all sixteen |
| **Phase 15** | Must not build a per-request authorization gate, must not revive `can_publish_ad` | BLOCK 8's admin contract asserts **field and action reachability**, not permissions. `AUTHZ-005` rejected the dead-code label on `can_publish_ad`; this plan does not revive it |
| **Any phase — the audit input** | Must not edit `.ai/audit/**`, another phase's plan, or `src/telegram_bot/tests/conftest.py` | 29 `.ai` entries show as changed at this anchor (tracked `.ai/audit/**` deletions plus untracked artefacts). `git status --short .ai` must show **no new modifications** beyond them and this plan's own file |

### 5.5 Shared-artefact reservations

| Artefact | Phase 11 claim | Conflict and rule |
|---|---|---|
| **`src/backend/conftest.py`** | **BLOCK 14** (`create_test_ad`, `create_test_ads_bulk` only) | **Eight-way. Q1.** Seven plans say "nobody" or "not at all"; phase 05 BLOCK 4 claims it; phase 11 needs it |
| `src/backend/conftest.py::_restore_test_schema_post_db_setup` | **read only** — it is `TEST-011`'s context and would be `TEST-003`'s natural home for a bound | Phase 03: "must not edit it at all". **BLOCK 5 uses a settings option instead, deliberately** |
| `src/telegram_bot/tests/conftest.py` | **read only** (C-9) | It **redefines** the fixtures because pytest's upward discovery never passes through `src/backend/`; it **shares** `create_test_ad`. Phase 05's claim that both must change is refuted |
| `.github/workflows/ci.yml` | **BLOCKS 2, 3, 4, 16** | Phase 01 owns the `lint`/`typecheck` jobs; phase 02 owns `deploy-check`; phase 09 BLOCK 15 holds part of it. Phase 11 touches the **pytest step, the artifact upload, and the two job timeouts only** |
| `.github/workflows/ci-nightly.yml` | **BLOCKS 2, 3, 4** | **Nobody.** Phase 11 is the first to touch it — which is why C-3 exists |
| `pyproject.toml` `[tool.pytest.ini_options]` | **BLOCKS 3, 4** | Phase 02 forbids new dependencies — **no dependency is added**. Nobody else edits this table. `[tool.coverage.*]` is read by BLOCK 2 but **not edited** |
| `config/settings/test.py` | **BLOCK 5** | **Test configuration, not production.** Phase 03 `DB-004` sizes the matching production bound |
| `apps/search/tests/test_search_view.py` | **BLOCK 9** | **12-way.** Ordering in §5.2 |
| `apps/search/tests/test_search_query_count.py`, `test_search_slo.py` | **nobody** | 2–3 phases' tripwires; phase 11's are to be *respected*, not edited |
| `apps/core/tests/test_advisory_lock_ids.py` | **nobody** | Six phases. Phase 11 allocates no lock id |
| `apps/core/tests/test_ad_image_delete_signal.py`, `test_delete_photo_single_call.py` | **BLOCK 7** | 3 phases. Phase 11's scaffold first (C-4) |
| `apps/core/tests/test_advisory_lock_release_log.py` | **nobody** | Phase 03 BLOCK 2's |
| `apps/moderation/tests/test_approve_ad_side_effects.py` | **BLOCK 7** | 5 phases. Ordering in §4.1 row 7 |
| `apps/core/tests/test_support_admin.py` | **BLOCK 8** | Phase 06 BLOCKs 12/13. Phase 11 extends |
| `apps/search/tests/test_autocomplete.py` | **BLOCK 10** | Phase 08 BLOCK 5 |
| `apps/core/tests/test_migrations.py`, `config/settings/test_migrations.py` | **BLOCK 13** (extend only) | Phase 02 BLOCKs 3/4/5/9 |
| `.kilo/rules/commands.md`, `docs/99-agent/rules.md` | **BLOCK 14** (same commit as the flip) | Both document the wrong `create_test_ad` default. Phase 01 edited `docs/99-agent/rules.md` |
| `.kilo/commands/audit/phases/11-audit-test-coverage.md` | **BLOCK 16** | Nobody. An audit **input**, not an audit artefact |
| `src/backend/testing/moderation_fixtures.py` | **BLOCK 15** (Q10) | Nobody |
| `src/backend/apps/**/tests/**` (the 62 defaulted call sites) | **BLOCK 14** (mechanical, one line each) | Overlaps phase 05's triage and phase 10 BLOCK 9's `test_priority.py` work. **Phase 11 changes no assertion in any of them** |
| `.ai/audit/**` | **nobody.** Unmodifiable by mandate | No block may restore `11-test-coverage/findings.md` |

### 5.6 What phase 11 needs from other phases (forward dependencies)

1. **Phase 03 `DB-002` landed**, or phase 11 BLOCK 5 is folded into it. Without this, BLOCK 5
   does not start — `record_event` swallows the `OperationalError`.
2. **Phase 03 `DB-004`'s value**, so BLOCK 5's test-side value can be reconciled with it
   rather than chosen independently.
3. **Phase 07 `MEDIA-001` sequenced after BLOCK 7's scaffold**, or BLOCK 7 folded into
   phase 07's commit.
4. **Phase 08 BLOCK 3 (NUL fix), BLOCK 1 (`SRCH-001` cap) and BLOCK 5 (`UniqueConstraint`)**
   — each is a same-commit-with-production-change gate on BLOCKS 9, 6 and 10.
5. **Phase 06 `VAL-007`** as the scoping input to BLOCK 8, and **phase 02's**
   `test_migrations.py` shape as the input to BLOCK 13.
6. **Phases 04 and 06's predicates landed** before BLOCK 12's predicate-equality test.
7. **The coordinator's answer to Q1** (conftest ownership) and to **Q2** (AD-008 branch) —
   the two blockers, without which BLOCK 14 never starts.
8. **Phase 01's `ENT-004` block**, so BLOCK 16 knows whether its CI-scope item is already
   shipped (Q12).

---

## 6. Out of scope for this plan

Every de-scoping below is **routed**, not dropped. A de-scoped item with no destination is a
re-filed finding.

### 6.1 De-scoped by design (deliberately not done here, with the rationale)

| Item | Why |
|---|---|
| **Phase 10's two routed AST architecture rules** (`CQ-002`, `CQ-004`) | Phase 10's own reasoning is *"a rule that must first be made true cannot be enforced before it is true"*, and both would false-positive on ~26 legitimate `AppConfig.ready()` deferrals and on the `request.POST` + `save()` delegate in `moderation/views/review.py`. **Upheld and recorded** (Q11). Building them would be §1.5's mirror test at scale — a rule that encodes the current shape of the code |
| **The `?features=` production cap, and a `max_length` on `feature_slugs`** | **Phase 08's** (`SRCH-001`, already validated CRITICAL). Phase 11 files the coverage gap and the test-hostability prerequisite. Re-filing the cap would ship the same change twice |
| **The production `statement_timeout` / `lock_timeout`** | **Phase 03's** (`DB-004`, `DB-002`). Phase 11 ships only the test-side half, and hard-blocked on `DB-002` |
| **`PopularSearch`'s `UniqueConstraint` and migration** | **Phase 08 BLOCK 5's.** Phase 11 writes the introspection test. **This plan ships no migration** |
| **`MEDIA-001`'s reference check inside the `on_commit` callback** | **Phase 07's.** Phase 11 ships the scaffold that verifies it. Doing both here would put the fix and its verification in different phases, which is the failure mode the scaffold exists to prevent |
| **Any `AdvisoryLockId` allocation** | Six phases name `test_advisory_lock_ids.py`. Phase 11 allocates none and does not edit that file. **A new member is a three-files-one-commit unit** (`enums.py` + `advisory_lock.py`'s allocation docstring + the guard test), with the coordinator told first |
| **The `squash_rehydrate_runsql` *migration*** | **It does not exist** (C-7). The *command* exists and has 4 passing tests. A finding premised on testing a non-existent migration is a finding with nothing to test |
| **Tests for the six confirmed false positives** | `AccountStateMiddleware._resolve_user`/`._evaluate_user_state` (46 tests), `listings.py::_suggest_category`, `favorite.py::toggle_favorite`, `swr_cache.py`'s private entry helpers, `alert_query.py`'s three private helpers, `auto_moderation.py`'s seven private validators, `core/utils/cache.py`'s nine wrappers. The name-reference method flags them; they are covered. **Writing tests for them would add coverage of already-covered code and increase regression surface** |
| **Tests for `show_metrics` / `profile_queries`** | Zero references, but a management command's usefulness is measured by use, and `profile_queries` is performance tooling. **Routed, not tested** |
| **`djlint_custom_rules.py`, `ad_data/keyboards.py`, `feature_helpers.py`** | Tooling and presentational helpers in the bot tree. Zero references is not a defect. **No finding covers them** |
| **The `_run_in_subprocess` consolidation** | Phase 02 §5.2 routed it to "phase 10 / **phase 11**". **Phase 11 declines it.** It is not a test-coverage finding, it touches four phases' test files, and phase 02's own BLOCKs own the shape |
| **`--reruns`** | `pytest-rerunfailures` is installed and unconfigured — but re-running a failed test in a suite where `TRUNCATE … CASCADE` races across xdist workers can **mask** a real teardown failure. The finding asks for a timeout; the rerun half is de-scoped with the reason recorded |
| **Consolidating `test_slo_constants.py` and `test_search_slo.py::TestSLOConstants`** | The same five `PerformanceSLO` values are asserted in two files — real duplication. But it touches the file CI runs as a **separately named gate**, and the payoff is cosmetic. **Routed as a follow-up**; not worth a block in a plan whose scarce resource is coordination |
| **A coverage number, a pass rate, a wall-clock baseline** | No coverage run, no full suite run, and no timing measurement was performed for this plan, and none is proposed. BLOCK 2 *reads* the number Q2 requires and does not manufacture one |
| **Reproducing the superlinear `?features=` planner cost** | Phase 08's probe terminated the PostgreSQL cluster twice — 22 databases offline. **Phase 08's `ANALYZE` numbers are authoritative and this plan does not reproduce them** |

### 6.2 Not phase 11's because a rule forbids it

| Item | Why |
|---|---|
| Editing production code to make a test pass | Project rule 3: **production code is king.** Where a phase-11 test fails against a real defect (`AUT-005`, `PII-103`, `AD-001`, `PII-107`), the test is **routed to the owning phase**, not fixed here |
| Re-filing `ENT-004` | The typecheck gate is green (C-2). Phase 01 owns the root cause. Re-filing ships the same fix twice at a different severity — the `CQ-002` → `ENT-005` mistake, once more |
| Expanding another phase's required test rewrite into new coverage | Stated by phases 05, 06, 07, 08, 09 and 10 in their own §5s. Phase 11 honours it in both directions |
| Editing `.ai/audit/**` | Unmodifiable by mandate. 29 `.ai` entries show as changed at this anchor (tracked deletions plus untracked artefacts); no new modification may be added |

### 6.3 Recorded as refused

| Item | Decision | Where |
|---|---|---|
| A blanket "no identity column may be writable in any generated admin form" rule | **Refused as stated.** It false-positives on `SupportContactAdmin.telegram_id` — a support *channel* id, not a data-subject field. Phase 06's `VAL-007` requires an explicit declared set. Q7 option (c) is the only form that carries one | BLOCK 8 |
| Deleting all 27 `getsource` assertions | **Refused.** It deletes a shipped phase-01 hard regression guard (`TestSessionLockLogging`) and two lock-order assertions, from files five phases hold | BLOCK 11, Q8 |
| Marking `apps/media/tests/test_sweep_orphaned_media.py` as `transaction=True` so the scaffold passes | **Refused.** Changing another phase's test to suit this block is the mirror-test failure in a different costume | BLOCK 7 |
| Introducing the first `skip` / `skipif` / `xfail` marker in the suite | **Refused.** The suite has **zero**. A conditional test is a test that can silently stop running, and no block may introduce one | BLOCKS 6, 10 |
| Changing `-q` to surface the seed header | **Refused.** An artifact upload records the seed without reformatting every CI log and every developer's terminal | BLOCK 4 |

---

## 7. Per-block risk register

Severity here is **this Planner's assessment of execution risk for the change**, not the
finding's severity. "Contention" covers shared files and shared ownership. "Correctness"
covers whether the suite still says what it is supposed to say. "Corpus" covers global or
cross-cutting changes. **Every row's "mirror" kind is the risk of writing a test that only
restates the implementation** — §1.5's question.

| Block | Risk | Kind | Likelihood | Impact | Mitigation / detection | Residual |
|---|---|---|---|---|---|---|
| **All** | An implementor works from the **report's** numbers and migrates 111 sites, or opens `apps/users/tests/test_unsubscribe.py`, or asserts a `squash` *migration* exists | Process | Med | **High** | C-1, C-5, C-7 are in §0.2 and every affected block's binding constraints; §4.1 names the correct paths | Very low |
| **All** | A block runs with its gate unanswered, or the Implementor silently picks an option | Process | Med | **High** | Every gate is a labelled block in §3 and a row in §0.5; §8.1 checks a **written** answer exists for each | Low |
| **All** | A test that **mirrors the implementation** is added — passes for the wrong reason, or breaks on an equivalent refactor | **Mirror** | Med | **High** | §1.5's question is asked in every coverage block; BLOCK 6 requires a negative control, BLOCK 7 requires a per-test sentinel, BLOCK 8 forbids snapshotting the field list, BLOCK 11 writes the rule | Low |
| **All** | A block's tests are **asserted** rather than run, or run on the host where there is no database | Process | Med | **High** | Every block names its exact Docker command; tests run **only** through the `test` service (§1.1) | Low |
| **All** | A red gate is captured while another phase agent runs, and a teardown race is reported as a product defect | Process | **High** | Med | Concurrent runs collide on one `test_mko_bazuna`. Re-run serially before reporting. The symptom is `test_mko_bazuna does not exist` / `relation "..." does not exist` | Low |
| **All** | A `PYTEST_OPTS` value is quoted, so the tokens word-split and the run silently tests the wrong thing | Process | Med | Med | §1.1 states the unquoted expansion; every targeted command in §3 uses the bare-token form and adds `--reuse-db` explicitly | Low |
| **All** | A blanket `ruff check --fix src/` reorders imports another phase's uncommitted work depends on | Process | Med | Med | `[tool.ruff] fix = false` is set deliberately; `--fix` is scoped to the block's own files (§1.2) | Low |
| **All** | A source-inspection test is **deleted** to make another phase's move green, removing the only guard on a locking structure | Correctness | Med | **High** | §1.3 rule 3, §4.5 item 10, and BLOCK 11's rule names the assertions that must survive | Low |
| **All** | A green test that **encodes a defect** is treated as the specification | Correctness | Med | **High** | Project rule 2, restated per block. BLOCKS 9 and 10 forbid `pytest.raises(DataError)` / `MultipleObjectsReturned` as a pass condition; BLOCK 8 says a red arrival is *routed*, not deleted | Low |
| **All** | A count sized at `6413df5` is used without re-measurement | Process | **High** | Med | C-1 and C-8: the `ON_MODERATION` count moved 111→124 and the typecheck errors 12+2→0 **between two anchors with nobody editing the tests**. BLOCK 1 re-measures; §0.2.3 is a baseline, not a truth | Med — accepted |
| **All** | A new user-visible string ships without non-empty `ru` **and** `bs` | i18n | Low | Med | **No block in this plan adds a string.** `locale/**` is untouched by all sixteen; `test_i18n_completeness.py` is a tripwire here | Very low |
| **1** | The schedule is produced but not read, and phase 14 starts against a stale map | Process | Med | **High** | §4.1 is a first-class output and §8.2 requires the schedule to be checked against plans 03–10 before BLOCK 2 starts | Low |
| **1** | `11-TEST-013` is recorded closed without Q12's answer, and a phase reintroduces the red gate | Process | Med | Med | Q12 is a gate; BLOCK 16 depends on its result; §8.1 checks the written answer | Low |
| **2** | `fail_under = 80` starts firing and CI goes red on arrival with no way to tell whether coverage is genuinely short or branch coverage is newly counted | Rollout | **High** | **High** | **Q2's second half**: measure first, under option (a) or (b). The commit body names the option and the measured number | Low |
| **2** | Only `ci.yml` is fixed and `ci-nightly.yml` keeps measuring the inert configuration | Correctness | Med | **High** | C-3; binding constraint 1 makes it a review rejection | Low |
| **2** | `testpaths` is "fixed" for a non-problem, and one of the two trees stops being collected | Behaviour | Low | **High** | Binding constraint 2. The bot tree is already collected — `rootdir` discovery walks upward; only coverage's config search does not | Low |
| **3** | The ceiling is chosen from imagination and reds the nightly's `seed` bulk cases | Rollout | Med | Med | Binding constraint 2 requires an observed slowest case; both workflows get their own value | Low |
| **3** | `timeout_method = "thread"` is chosen, the timeout returns, and the runaway statement keeps running | Correctness | Med | **High** | Option (c) is listed and rejected in the gate table; binding constraint 2 makes the observed case the input to the choice | Low |
| **3** | A global `timeout` reds `TestSearchResponseSLORegression` or `test_lookup_cache_swr`'s deliberate `sleep(0.2)` | Regression | Med | Med | Both are named in the gate table; both are in the block's acceptance criteria | Low |
| **4** | `--randomly-seed` is pinned and shuffle detection is silently switched off, so an order-dependence bug stops being found every run | Correctness | Med | **High** | Q5 states option (a)'s cost in its own row; binding constraint 5 makes the trade-off mandatory in the commit body | Med — accepted, by decision |
| **4** | The artifact is uploaded from the wrong working directory and contains no seed | Correctness | Low | Med | Binding constraint 2 names `rootdir` | Very low |
| **4** | A conftest fixture is added to log the seed, dragging the most contended file into this plan | Contention | Med | **High** | Binding constraint 3 names Q1's blocker explicitly as the reason not to | Low |
| **5** | The bound lands before phase 03 `DB-002` and `record_event`'s swallowed `OperationalError` becomes a new analytics failure mode | **Correctness** | Med | **High** | Hard external gate; §4.5 item 2; binding constraint 6 says the fix is "DB-002 has not landed", not "widen the timeout" | Low |
| **5** | `SET LOCAL` is reinstated "as a cleanup" and is a no-op for all 48 `transaction=True` scopes | Correctness | Med | **High** | Option (c) is rejected **in the gate table** with the reason; binding constraint 2 restates it so it cannot re-enter as tidying | Low |
| **5** | A conftest session fixture is used instead of a settings option, and BLOCK 5 lands behind BLOCK 14's blocker | Contention | Med | Med | Option (b) is listed with that cost stated; binding constraints 1 and 2 | Low |
| **5** | The chosen value reds the slowest legitimate statement — `migrate --run-syncdb`, `TRUNCATE … CASCADE`, or the `search` SLO path | Regression | Med | Med | Acceptance criteria name all three; the value is a named constant so DB-004's can be diffed against it | Low |
| **6** | The test provokes the unbounded query and takes the shared instance offline for 22 databases | **Rollout** | **Med** | **High** | Hard edge on BLOCK 5 (§4.5 item 1). Never run the reproduction by hand; BLOCK 6's negative control is a *test*, run inside the bound | Low |
| **6** | The test passes because the parameter was silently dropped, and the runaway class stays unobserved | **Mirror** | Med | **High** | Binding constraint 5 and the negative-control acceptance criterion: it must fail distinguishably against the uncapped implementation | Low |
| **6** | The test lands as a red commit in phase 11, and the one-commit rule is violated | Process | Med | Med | Q6 option (a) is the default recommendation; binding constraint 1 | Low |
| **7** | The scaffold looks right and **never fires** the callback — the worst outcome, because it converts "unverified" into "verified-looking" | **Mirror** | Med | **High** | Binding constraint 1 requires a **sentinel per test** (a counter, a touched file, a written row), not an assertion that nothing happened | Low |
| **7** | The scaffold lands **after** MEDIA-001 and a refcount bug ships verified by 7 tests with 8 media files blind to it | **Rollout** | Med | **High** | Q7' option (c) is listed and rejected; §4.5 item 7; C-4 quantifies the surface | Low |
| **7** | The new tests are placed outside a `transaction=True` scope, or `test_sweep_orphaned_media.py` is re-marked so they would pass | **Mirror** | Med | Med | Binding constraints 1 and 6. Re-marking another phase's test is §6.3, refused | Low |
| **7** | `test_advisory_lock_release_log.py` is edited, colliding with phase 03 BLOCK 2 | Contention | Low | Med | Binding constraint 3; §4.1 row 6 | Very low |
| **8** | A blanket data-subject rule false-positives on `SupportContactAdmin.telegram_id`, a support *channel* id | Correctness | **High** | Med | Phase 06 `VAL-007` is mandatory and is an explicit gate (Q7); binding constraint 1; a row in the block's acceptance criteria | Low |
| **8** | The test enumerates today's field list as correct — the `getsource` failure mode in a new coat | **Mirror** | Med | **High** | Q7 option (b) is rejected for exactly this; binding constraint 1 forbids it; the acceptance criteria list contracts, not lists | Low |
| **8** | A test fails on arrival and is deleted, removing the admin surface's only audit | Correctness | Med | **High** | Binding constraint 4: a red arrival is routed to the owning phase and named in the commit body | Low |
| **8** | `test_support_admin.py` is rewritten rather than extended, colliding with phase 06 BLOCKs 12/13 | Contention | Low | Med | §4.1 row 8; binding constraint 2 | Very low |
| **9** | `test_search_view.py` is edited without re-reading it, and phase 08's or phase 10's uncommitted change is clobbered | **Contention** | **High** | Med | §5.2 fixes the order; the block's re-read instruction and acceptance criteria make the check explicit; stop-and-report on a concurrent change | Med — accepted |
| **9** | The C0 case asserts the current `DataError` as the expected outcome | **Mirror** | Med | **High** | Binding constraint 2; an acceptance criterion forbids `pytest.raises(DataError)` on any `?q=` path | Low |
| **9** | The corpus adds a query or slows the render, and the SLO gate starts failing | Performance | Low | Med | `test_search_query_count.py` and `test_search_slo.py` are in the acceptance criteria and are **not** edited | Low |
| **10** | The `Meta.constraints` test commits before phase 08's migration and is red on arrival | Process | Med | Med | Q7'' options (a)/(b)/(c) all handle it; option (c) defers only the introspection half, and the concurrency half ships regardless | Low |
| **10** | The introspection test asserts the constraint's `name` and turns red on a rename | **Mirror** | Med | Med | Binding constraint 2: presence and semantics, never the literal name | Low |
| **10** | The two-thread test uses `time.sleep` to force overlap and becomes timing-dependent | Correctness | Med | Med | Binding constraint 3 requires the commit body to say so if it does. The `test_lookup_cache_swr.py` precedent is named, not copied | Low |
| **10** | A `skipif` is introduced to make the introspection test conditional — the first in the suite | Correctness | Low | Med | Binding constraint 1 forbids it; §6.3 refuses it | Very low |
| **11** | All 27 are deleted, removing `TestSessionLockLogging` and two lock-order assertions | Correctness | Med | **High** | Q8 option (c) is listed and the Implementor may not choose it; binding constraints 2 and 5 | Low |
| **11** | The rule is written and never enforced, and the next phase re-litigates the file | Process | Med | Med | Binding constraint 1 requires the rule to be committed before any assertion is touched | Low |
| **11** | `test_admin_pii_containment.py` is deleted and BLOCK 8 was de-scoped, so the admin surface loses its only audit | **Rollout** | Low | Med | BLOCK 8 is an explicit dependency; the acceptance criteria require BLOCK 8's coverage before the deletion | Low |
| **12** | A bot-side test calls the ORM directly and deadlocks or corrupts teardown instead of failing cleanly | Correctness | Med | Med | The `sync_to_async` rule is a binding constraint; the acceptance criteria forbid a direct call | Low |
| **12** | The predicate-equality test ships before either predicate is landed and asserts a defect as correct | **Mirror** | Med | **High** | External gate on phases 04 and 06; binding constraint 4; the acceptance criteria say *routed, not written* | Low |
| **12** | A harness is built that runs the real bot process inside pytest | Scope | Low | **High** | Binding constraint 1 — the report's own proposal 3, endorsed | Very low |
| **12** | A new bot fixture is added to `src/telegram_bot/tests/conftest.py` for one test | Contention | Med | Med | Binding constraint 2; the block reuses `sync_to_async` and `Client` instead | Low |
| **13** | The effect test is written in the **default** suite and passes for the wrong reason — `syncdb` has no migration preconditions | **Mirror** | **High** | **High** | Binding constraint 1: the test does not run under `config.settings.test_migrations` against `test_migration_repro`, it does not ship. Acceptance criteria name the database | Low |
| **13** | It targets the squash *rehydrate* migration, which does not exist | Process | Low | Med | C-7; the four real targets are named in the block and §2 | Very low |
| **13** | It collides with phase 02's BLOCKs 3/4/5/9 on `test_migrations.py` | Contention | Med | Med | §4.1 row 10; binding constraint 5 — extend the shape, never rewrite phase 02's tests | Low |
| **13** | The subprocess command is written non-bandit-clean and trips phase 02's `VAL-006` fix when it newly scans the whole repo | Contention | Low | Med | §5.4 phase-09 row: list-form `subprocess.run`, no literal temp path | Very low |
| **14** | The file is edited and seven plans' "nobody" statements become false in one commit | **Contention** | Med | **High** | **Q1 is a hard blocker.** The commit body names the Q1 option and the ruling | Low |
| **14** | The 62-site pass is done and `AD-008` is then fixed by making `ON_MODERATION` durable, invalidating it | **Rollout** | Med | Med | **Q2 is a hard blocker.** Under Q2(a) the pass is skipped by design, and that is a *successful* outcome of this block | Low |
| **14** | Phase 05's "both conftests must change together" is acted on and the bot conftest is edited for nothing | Process | Med | Low | C-9; binding constraint 5; the acceptance criteria require it unmodified | Very low |
| **14** | `_set_status_timestamp` is changed "to add an `ON_MODERATION` branch", and the block scope creeps | Correctness | Low | Med | Binding constraint 3 names the function as read-only and explains the phantom-`IntegrityError` chase | Very low |
| **14** | Only one of the two rule files is corrected, leaving the drift half-fixed | Correctness | Med | Med | Binding constraint 4: both in the same commit as the flip; project rule 14 | Low |
| **14** | The regression guard is omitted and a third drift lands after this block | Correctness | Med | Med | Binding constraint 6; an acceptance criterion requires it to fail on a reverted default | Low |
| **15** | A test is written for a symbol another phase owns, and two tests must be kept in step | Scope | Med | Med | The ownership table is the block's primary output; binding constraint 1 | Low |
| **15** | A test is written for a confirmed false positive, adding regression surface to covered code | Correctness | Med | Med | Binding constraint 2; the false-positive list is named in §3 with the reason for each | Low |
| **15** | `moderation_fixtures.py` is deleted before its purpose is investigated | **Rollout** | Med | Med | Q10's table states the dead-code policy in option (b)'s own cell; the acceptance criteria require the investigation first | Low |
| **15** | Q10(a) is chosen and `src/backend/conftest.py` is edited through the back door | Contention | Low | **High** | Binding constraint 3: Q10(a) **and** Q1 must both be satisfied; otherwise the default is not to edit | Low |
| **16** | The handbook is corrected before BLOCK 2 lands, and the commit asserts a falsehood about a system that is about to change | Correctness | Med | Med | Hard edge `2 → 16` (§4.3); acceptance criterion 3 | Low |
| **16** | A CI step is added that phase 01 already shipped, duplicating the lint/typecheck scope | Contention | Med | Med | Q12; binding constraint 5 | Low |
| **16** | The handbook edit is treated as an audit-artefact edit and lands under `.ai/audit/**` | Process | Low | Med | Binding constraints 1 and 3; `git status --short .ai` in the acceptance criteria | Very low |

---

## 8. Definition of done for the whole plan

Phase 11 is complete when **all** of the following hold.

### 8.1 Scope

- [ ] All 16 finding-units have a recorded disposition: **14 implemented or gated**,
      **1 already fixed** (`11-TEST-013` — closed, with Q12's answer recorded),
      **1 stale** (`11-TEST-001`'s count corrected to 124), **0 rejected**,
      **0 dropped without a destination**.
- [ ] Every gated block (**2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16**) has a
      **written** answer for each of its open questions, naming the option chosen and the
      consequences accepted. **Silence is not an acceptable outcome for any of them.**
- [ ] Each of **Q1 … Q12** is answered with a record or explicitly re-routed with a named
      destination. **Q1 and Q2 are coordinator / phase-05 rulings** (the two blockers);
      **Q12 is an Auditor finding from the commit log**; **Q3–Q6 and Q8, Q9, Q11 are Planner
      decisions**; **Q7 needs phase 06's `VAL-007`**; **Q7' and Q7'' need the coordinator**;
      **Q10 is a Researcher judgement**; **Q8' is a Planner shape choice**.
- [ ] **Q1 and Q2 are answered before BLOCK 14 started**, not after.
- [ ] Every de-scoping in §6 has a named destination or a stated rationale, and the five
      refusals in §6.3 are recorded as refusals.
- [ ] `CQ-002` / `CQ-004` were **not** built, and the refusal is recorded with phase 10's
      reasoning.

### 8.2 The deliverable — the ordered test-change schedule

- [ ] The §4.1 schedule exists with one owning phase, one phase-11 block and one ordering
      rule for each of its 18 contested artefacts.
- [ ] The schedule was **checked against plans 03, 04, 05, 06, 07, 08, 09 and 10** before
      BLOCK 2 started, and every disagreement was escalated to the coordinator.
- [ ] `src/backend/conftest.py` has exactly one owning phase, recorded.
- [ ] Each of the four top-conflict files — `conftest.py`, `test_search_view.py` +
      `test_search_query_count.py` + `test_search_slo.py`, `test_advisory_lock_ids.py`,
      `test_ad_image_delete_signal.py` — has one owner and one rule, and **no block in this
      plan or any other touched a file without checking it**.
- [ ] If plans 12–15 landed during execution, their §5 sections were re-read and the §5.4
      table extended before their first block.

### 8.3 Gates — all green

- [ ] `uv run ruff check src/` → **All checks passed, exit 0** (unchanged from the anchor).
- [ ] `uv run basedpyright .` from `src/backend` → **0 errors**.
- [ ] `uv run basedpyright .` from `src/telegram_bot` → **0 errors**.
- [ ] `.\Makefile.ps1 test` → fast gate green (`seed` marker skipped), run **after every
      block**, not only at the end.
- [ ] `makemigrations --check` → **no changes**. **This plan ships no migration.**
- [ ] `apps/ads/tests/test_i18n_completeness.py` green after every block.
- [ ] `apps/search/tests/test_search_query_count.py` and `test_search_slo.py` green and
      **unmodified** — no phase-11 block edited either.
- [ ] Every red-gate observation was **re-run serially** before being reported as a defect
      (§1.1).
- [ ] `git status --short .ai` shows **no new modifications** beyond the pre-existing
      `.ai/audit/**` deletions and this plan's own file.
- [ ] No commit was made without an explicit user request; no `git reset`, `git checkout`,
      `git restore` or `git stash` was run at any point; no other agent's uncommitted change
      was staged or reverted.

### 8.4 Per-item behavioural confirmation

- [ ] **`11-TEST-002`** — the CI log contains `Required test coverage of 80.0% reached` (or
      Q2's recorded outcome); the term report shows `Branch` / `BrPart`; `src/telegram_bot`
      is in the measured source set; `testpaths` unchanged and both trees still collected;
      **`ci.yml` and `ci-nightly.yml` both fixed**.
- [ ] **`11-TEST-003`** — a statement exceeding the bound is cancelled **both** in a
      `transaction=True` test and in a transactional one; `migrate --run-syncdb` completes
      under the bound; `TestSearchResponseSLORegression` green; `config/settings/base.py`,
      `production.py`, `dev.py`, `local.py` untouched; the hostile-`?features=` test fails
      distinguishably against the uncapped implementation and passes under the bound and
      phase 08's cap; `test_features_filter.py` green unchanged.
- [ ] **`11-TEST-004` + `11-TEST-014`** — each new test carries a sentinel proving the
      `on_commit` callback fired; the rollback cases failed before the commit and pass after;
      **no new test patches `transaction.on_commit` away** and the two existing patches in
      `test_approve_ad_side_effects.py` are replaced rather than duplicated; the three
      existing `test_ad_image_delete_signal.py` tests green unchanged;
      `test_advisory_lock_release_log.py` and `test_sweep_orphaned_media.py` untouched.
- [ ] **`11-TEST-005`** — assertions are on observable fields, not ORM paths; every bot-side
      DB call goes through `sync_to_async`; no new fixture; the real bot process is not
      started by any test; the predicate-equality test shipped only if both predicates were
      landed.
- [ ] **`11-TEST-006`** — each C0 case asserts HTTP 200 and a result set; no
      `pytest.raises(DataError)` on any `?q=` path; `test_search_query_count.py` and
      `test_search_slo.py` green unchanged.
- [ ] **`11-TEST-007`** — the two-thread test is distinguishable against a non-unique column;
      `makemigrations --check` reports no changes; no `skip` / `skipif` / `xfail` introduced;
      the introspection test asserts fields and semantics, not the constraint's name.
- [ ] **`11-TEST-008` / `11-TEST-009`** — a failed CI run's seed is recoverable per Q5, and
      the commit states whether shuffle detection was reduced; `-q` unchanged; a deliberately
      hanging test is killed and the failure names it; both workflows carry
      `timeout-minutes`; no marker and no conftest fixture added.
- [ ] **`11-TEST-010`** — the rule is committed and classifies all 27 assertions;
      `TestSessionLockLogging`, `TestResolveOwnedLocking`'s two order assertions and all
      three AST-source tests are green and unmodified; each deleted assertion is named
      individually; **the diff contains no source file outside `tests/`**.
- [ ] **`11-TEST-011`** — each effect test runs against the migration database and names it;
      `ads/0003` leaves exactly one DRAFT per user and `ads/0004`'s constraint applies;
      `search/0002` leaves no original digits; the existing applicability and idempotency
      tests green unchanged; **no migration created, altered or deleted**.
- [ ] **`11-TEST-012`** — every registered `ModelAdmin`'s generated form is inspected and its
      identity columns and password-bearing fields asserted non-writable; every admin
      declaring `actions` is asserted reachable through `get_actions(request)`;
      `SupportContactAdmin.telegram_id` does not false-positive; **no assertion enumerates
      today's field list**; any test red on arrival was routed, not deleted; no production
      admin modified.
- [ ] **`11-TEST-013`** — `basedpyright` green in both scopes; `ruff check src/` clean;
      Q12's answer recorded; the CI-scope item shipped **only if** phase 01 had not already
      done it; the handbook no longer asserts an 80 % branch coverage gate nor "9 files".
- [ ] **`11-VAL-001` / `11-VAL-002`** — the re-measured census is recorded with its anchor
      and both old and new numbers where they differ; the `on_commit` exposure is counted
      **once**; **`.ai/audit/11-test-coverage/findings.md` was not restored**.
- [ ] **`11-TEST-001`** — every call site passes `status=` explicitly and the defaulted count
      is zero; both factory defaults are `AdStatus.PUBLISHED`; `_set_status_timestamp` is
      byte-identical; both rule files corrected in the flip commit; the regression guard fails
      if the default is reverted; **`src/telegram_bot/tests/conftest.py` unmodified**; no
      production file touched; `makemigrations --check` clean.

### 8.5 What this plan did not do, restated so it cannot be read as incomplete

- [ ] No production code was modified. Zero.
- [ ] No schema change and no migration.
- [ ] No new test framework, harness, fixture layer, conftest or marker.
- [ ] No new user-visible string and no locale file touched.
- [ ] No other phase's plan and no `.ai/audit/**` file modified.
- [ ] No test deleted to make another phase's change green.
