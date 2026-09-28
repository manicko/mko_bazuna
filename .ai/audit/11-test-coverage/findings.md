# Phase 11 — Test Coverage & Test Suite Quality Audit

**Date:** 2026-09-28
**Phase file:** `.kilo/commands/audit/phases/11-audit-test-coverage.md`
**Mode:** `problems_only = TRUE` — passes are recorded in Appendix B, not as findings.
**Anchor commit:** `0c91666` (`docs: pre-audit report of bot middleware suite (36k lines / 190 tests)`)
**Code changed:** none. No test file, source file, fixture or CI file was modified.

**Finding-ID prefix:** `TEST-`. The phase file §10 specifies `TST-`, but `TST-001…TST-005` are
already hard-coded as in-source provenance markers in shipped code
(`apps/users/tests/test_auth_service.py:10`, `apps/moderation/tests/test_moderation_views.py:13`,
`apps/ads/tests/test_edit_views_locking.py:15`). Following the task instruction, this report uses
`TEST-` so nothing collides. Key the remediation tracker on `11-TEST-0NN`.

---

## 1. Executive Summary

The suite is large, fast and, on its own terms, green: **2394 passed, 0 failed, 0 skipped in
226 s** (`.\Makefile.ps1 test`, `seed` excluded); 401 s with `--cov`. It exercises the real ORM,real PostgreSQL FTS, real migrations and a real bot FSM. Several areas are genuinely well covered
and the coverage gaps are not random — they are systematically concentrated in exactly the places
where the other audit phases found live defects.

The single root cause behind the most findings is that **the test fixtures manufacture data states
the production system cannot produce, and the mocks that manufacture them are the reason those
tests pass.** `create_test_ad` defaults to `AdStatus.ON_MODERATION`; `submit_ad` calls
`auto_moderate()` inside the same transaction and `auto_moderate()` always terminates into
`PUBLISHED` or `ON_MODERATION_FAILED`. 111 call sites in the test tree create `ON_MODERATION` rows.
Every consumer of that state — `approve_ad`, `bulk_approve`, the admin action, the moderation queue
statistic, the review views — therefore has a green test and an unreachable code path.

The second systematic gap is that **the coverage gate the project believes it has, does not run.**
CI executes pytest with `working-directory: src/backend`; coverage.py resolves its configuration
from the current working directory only, so `[tool.coverage.*]` in the repo-root `pyproject.toml`
is never read. `fail_under = 80` is not applied, branch coverage is off, `omit` is ignored, and
`src/telegram_bot` — the whole async Telegram process, which owns the ad-creation FSM, the
login-token claim and the contact deep link — is absent from the report CI produces.

| Dimension | Rubric verdict | Evidence |
|---|---|---|
| (a) Critical-path coverage | **Partially satisfied** | Lifecycle, contact gating, FTS visibility, consent well covered. Approval path and two-process consistency are not. |
| (b) Two-process consistency | **Not tested** | Zero tests cross the process boundary in either direction (TEST-005). |
| (c) LLM/external-API fallback | **Satisfied** | Translation fallback, circuit breaker and outage contracts covered (Appendix B). |
| (d) Test independence | **Satisfied** | Every DB test is transactional or `transaction=True`; session fixtures are `get_or_create`-idempotent. |
| (e) Mock discipline | **Partially satisfied** | ~600 mock assertions, but 3 tests assert the negative (`TEST-001`, TEST-010). |
| (f) Test database isolation | **Satisfied, with a blast-radius caveat** | Worker-DB separation is correct; nothing bounds a runaway query (TEST-003). |
| (g) Sensitive-data fixtures | **Satisfied** | Only reserved-domain emails and synthetic Telegram ID ranges (Appendix B). |
| (h) No forbidden calls | **Satisfied** | `pytest-socket` correctly absent; no real HTTP/DB escapes (Appendix B). |
| (i) Coverage threshold | **Configured but non-functional in CI** | TEST-002. |
| (j) CI gating | **Partially satisfied** | Lint + migrate checks pass; the typecheck gate is red (TEST-013). |

**Findings:** 13 total — **1 CRITICAL, 4 HIGH, 7 MEDIUM, 1 LOW**.
**Requires architectural or significant change:** TEST-001 (fixture contract rewrite),
TEST-002 (CI restructure), TEST-003 (per-test statement_timeout), TEST-005 (new test harness).

---

## 1a. Findings Summary

| ID | Severity | Title | Rubric dimension | Architectural? |
|---|---|---|---|---|
| TEST-001 | **CRITICAL** | `create_test_ad` defaults to uncommittable `ON_MODERATION`; 111 call sites fabricate it | CRITICAL: tests assert wrong business logic | **Yes** — fixture contract rewrite |
| TEST-002 | **HIGH** | CI never loads `[tool.coverage.*]` — no `fail_under`, no branch coverage, bot absent | (i) coverage threshold | **Yes** — CI restructure |
| TEST-003 | **HIGH** | No `?features=` bound test; one request kills the DB; the suite cannot host the test | (a), (f) | **Yes** — per-test `statement_timeout` |
| TEST-004 | **HIGH** | Alert `on_commit` ordering mocked away; no rollback-negative test | (a) | No |
| TEST-005 | **HIGH** | Two-process consistency untested in both directions | (b) | **Yes** — new test layer |
| TEST-006 | MEDIUM | No control-character case in `?q=` (NUL returns HTTP 500) | (a) | No |
| TEST-007 | MEDIUM | `PopularSearch`/`SearchHistory` dedup key untested under two writers; no DB constraint | (b), (a) | No |
| TEST-008 | MEDIUM | `pytest-randomly` seed unpinned and unrecorded | (i) | No |
| TEST-009 | MEDIUM | `pytest-timeout` / `pytest-rerunfailures` installed but never configured | (i) | No |
| TEST-010 | MEDIUM | 27 `inspect.getsource()` substring assertions, no behavioural value | (e) | No |
| TEST-011 | MEDIUM | `syncdb` schema means no test exercises a data migration's effect | (a) | No |
| TEST-012 | MEDIUM | No admin page is ever rendered or introspected | (a) | No |
| TEST-013 | LOW | `basedpyright` gate red (12 test-file errors); bot tree outside lint + typecheck | (j) — **owned by ENT-004** | No |

Cross-referenced, **not** re-filed: AD-008 / VAL-002 / VAL-003 (phase 05), SRCH-001 and the
`PopularSearch` UNIQUE constraint (phase 08), AUT-005 / PII-103 / PII-107 / AD-001 (phases 04/05/06),
DB-004 (phase 03), ENT-004 (phase 01), MEDIA-001/002 (phase 07).

---

## 2. Findings

### TEST-001 — `create_test_ad` defaults to an uncommittable ad state; 111 test call sites fabricate `ON_MODERATION`

**Severity:** CRITICAL
**Rubric item:** CRITICAL — *"Tests assert WRONG business logic and pressure production distortion."*
**Category:** `[SPEC-DEVIATION]` + structural
**Confidence:** High — re-derived from source and quantified by AST scan.
**Architectural / significant change required:** **Yes** — the fixture contract must change and 111
call sites must be migrated before AD-008 or phase-05 VAL-003 can be fixed.

**Evidence**

`src/backend/conftest.py:288-332` — the factory's *default* is the unreachable state:

```python
def create_test_ad(
    user: User,
    category: Category | None = None,
    city: City | None = None,
    *,
    status: AdStatus = AdStatus.ON_MODERATION,      # <- line 290
    ...
```

`src/backend/conftest.py:333-340` — the bulk factory repeats it: `status: AdStatus = AdStatus.ON_MODERATION`.

That state is never committed by any production path:

* `src/backend/apps/ads/services/submission.py:130-136` — `submit_ad` sets `ON_MODERATION`, then
  `:148` calls `auto_moderate(ad)` **inside the same `transaction.atomic()`** opened at `:119`.
* `src/backend/apps/moderation/services/auto_moderation.py:50-124` — `auto_moderate()` *always*
  terminates into `PUBLISHED` (`:82-88`) or `ON_MODERATION_FAILED` (`:91-124`).
* `ad_reactivate` (`submission.py:161-199`) does the same at `:188`.

So `ON_MODERATION` is a transient, never a committed state. Phase 05 filed this as **AD-008**;
its validator recorded it as **VAL-002** ("34 call sites in 10 test files") and **VAL-003** (the
human-approval path is dead code). Both are correct; this finding re-derives and **quantifies** the
test-side cost, and corrects VAL-002's count.

**Blast radius (AST scan of every `create_test_ad` / `create_test_ads_bulk` call in the test tree):**

| | count |
|---|---|
| Total call sites | 586 |
| `status=AdStatus.ON_MODERATION` passed explicitly | 49 |
| `status=` omitted → silently defaults to `ON_MODERATION` | **62** |
| **Total producing an `ON_MODERATION` row** | **111** |

Files, by call count: `apps/moderation/tests/test_moderation_views.py` (58 + 0), `test_admin_actions.py`
(17), `test_priority_service.py` (14), `apps/ads/tests/test_edit.py` (13), `test_submission.py` (11),
`apps/analytics/tests/test_moderation_analytics.py` (10), `test_moderation_side_effects.py` (8),
`test_submission_fixtures.py` (3), `apps/ads/tests/test_ad_detail_queries.py` (2),
`apps/core/tests/test_moderation_statuses.py` (1), `test_ad_constraints.py` (2),
`apps/api/tests/test_moderation_api.py` (6), `conftest.py` (the factory itself), plus 5 bot test files
(`test_ad_create.py`, `test_create_draft_ad.py`, `test_contact_gate.py`, `test_multi_lang_translation.py`,
`test_alerts_publish.py`).

**The mock is what makes it true.** The only backend-side test that asserts `submit_ad` commits in
`ON_MODERATION` replaces the deciding function:

```python
# src/backend/apps/ads/tests/test_submission.py:97-121
@mock.patch("apps.ads.services.submission.auto_moderate", return_value=True)
def test_submit_ad_commit_when_auto_moderate_passes(self, mock_am, ...):
    """... The mock bypasses the real ``_pass_moderation`` (which would set
    ``PUBLISHED``), so the ad stays at ``ON_MODERATION`` and ``submit_ad``
    returns True."""
```

The docstring documents the fabrication. The same pattern appears in
`test_edit.py:84-125` (`auto_moderate` → `True`, asserts `status == ON_MODERATION`) and
`test_edit.py:161+` (`auto_moderate` → `False`, asserts "remains at `ON_MODERATION`").

**What is green because of this:** `approve_ad`, `bulk_approve`, `AdAdmin.action_approve`, the
moderation review views, `get_pending_queue_size()` and the priority queue. Phase 05's validator
verified live that `bulk_approve` returns 0, the review-approve URL 404s, and `approve_ad()`
returns `False` for every real ad — while all 32 of phase 05's checks passed.

**Impact:** any remediation of AD-008 / VAL-003 is blocked until the tests stop asserting a state
the system cannot reach. "Fix the code" turns ~111 test sites red at once, and under delivery
pressure the temptation is to re-mock instead. This is the classic "tests pressure production
distortion" failure the rubric calls CRITICAL.

**Recommendation (tests change, production code untouched — production code is king):**

1. Change the default to `AdStatus.PUBLISHED` in both factories, so the fixture cannot silently
   produce an uncommittable state. Consider making `status` a *required* keyword for
   `create_test_ads_bulk` only, where the status is the interesting variable.
2. Migrate the 111 sites in one dedicated commit, grouped by file, with `ON_MODERATION` →
   `ON_MODERATION_FAILED` for the "auto-moderation rejected it" assertions and → `PUBLISHED` for
   the rest. This is mechanical; the judgement call is per-assertion intent.
3. Update `docs/99-agent/rules.md:53` and `.kilo/rules/commands.md:70`, which already document the
   default as `PUBLISHED` — they are currently wrong about the code.
4. Only then fix AD-008. Land 1–3 and the AD-008 production change in the same PR so the branch is
   never red across it.

**Effort:** M

---

### TEST-002 — CI never loads the coverage configuration: no threshold, no branch coverage, bot process absent from the report

**Severity:** HIGH
**Rubric item:** (i) *"No coverage reporting / threshold"* (rubric MEDIUM) escalated — see justification.
**Category:** `[SPEC-DEVIATION]` + CI configuration
**Confidence:** High — measured directly in the `mko-bazuna-test` image.
**Architectural / significant change required:** No source change; **yes as a CI restructure**
(one workflow step's working directory), because it also changes what the team believes it measures.

**Evidence**

`.github/workflows/ci.yml:133-138`:

```yaml
- name: Run pytest with coverage
  working-directory: src/backend      # <- line 133
  run: |
    uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short \
      --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db
```

`--cov` with no value means *"use the coverage config's `source`"* (verified in
`pytest_cov/plugin.py:100-116`: `cov_source` becomes `None`, so `self.cov` is constructed with
`source=None`). Whether those values are correct therefore depends entirely on coverage.py finding
`[tool.coverage.*]` — and coverage.py resolves its config from the **current working directory
only**; it does not walk up.

Measured inside the shipped test image:

```
CWD /app/src/backend  ->  config_file=None
                         branch=False  source=None
                         fail_under=0.0  omit=[]
CWD /app             ->  config_file=/app/pyproject.toml
                         branch=True   source=['src/backend','src/telegram_bot']
                         fail_under=80.0  omit=[7 patterns]
```

Running pytest the way CI does (from `/app/src/backend`) produces a report that differs in three
observable ways from the same command run from the repo root:

| | CI (`/app/src/backend`) | Local Docker `test` service (`/app`) |
|---|---|---|
| Branch columns in the header | **absent** (`Stmts Miss Cover`) | `Stmts Miss Branch BrPart Cover` |
| `Required test coverage of 80.0% reached` line | **absent** | present (`Total coverage: 85.89%`) |
| `src/telegram_bot/**` in the report | **absent** | present |

Local-run summary: `TOTAL 8693 stmts, 1051 missed, 1828 branch, 203 partial, 86%`. CI's file set
collapses to whatever is importable from `src/backend` — `apps/`, `config/`, `conftest.py`,
`testing/` — plus a few `/app`-absolute paths.

**Consequences**

1. **`fail_under = 80` is not enforced in CI.** `coverage.xml` is uploaded as an artifact
   (`ci.yml:140-143`) and *nothing can fail on it*. Coverage could fall to 30% and CI stays green.
2. **The async bot process contributes zero coverage to the CI number.** `src/telegram_bot` — 190
   tests, ~36 000 lines, and the owner of the ad-creation FSM, the `LoginToken` claim, the contact
   deep link and the alert delivery — does not appear in the report CI computes. Every phase in
   this audit that cited "86 %" was citing the local number.
3. **`omit` is ignored**, so `conftest.py` and `testing/moderation_fixtures.py` are measured as
   production code (the CI-style run shows `conftest.py` at 52 %, dragging the total).
4. **The local and CI numbers are not comparable**, which makes the threshold useless as a
   regression signal.

**Why HIGH rather than MEDIUM:** the rubric's MEDIUM covers "no coverage reporting or threshold".
Here a threshold exists in two places (config and CI) and is silently inert; the discrepancy is
invisible because the local path *does* enforce it; and the blind spot is precisely the half of
the system (the second process) for which the other phases found the thinnest test coverage.

**Recommendation — CI file only, no source change:**

```yaml
- name: Run pytest with coverage
  working-directory: .          # repo root: coverage config is found, source paths resolve
  run: |
    uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short \
      --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db
```

Verify by asserting the log contains `Required test coverage of 80.0% reached` **and** that the
term report lists `src/telegram_bot/`. If `working-directory: .` is unwelcome, the explicit form
is self-documenting:

```
--cov=src/backend --cov=src/telegram_bot --cov-branch --cov-fail-under=80 --cov-config=pyproject.toml
```

**Effort:** S

---

### TEST-003 — No test bounds `?features=`; one anonymous request terminates the PostgreSQL backend, and the suite cannot host such a test

**Severity:** HIGH
**Rubric item:** (a) critical-path coverage + (f) test-database isolation
**Category:** `[BEST-PRACTICE]` (coverage gap) + `[SPEC-DEVIATION]` (test isolation)
**Confidence:** High — reproduced twice on the shared test instance.
**Architectural / significant change required:** **Yes** — a per-test resource bound
(`statement_timeout`) is needed before the missing test can be written.

**Evidence — the gap**

`src/backend/apps/ads/services/listings_query.py:181-186` adds one correlated subquery-JOIN per
requested feature slug, with no cap on the list:

```python
for slug in feature_slugs:
    features_qs = (AdFeature.objects.filter(ad_id=OuterRef("pk"), feature__slug=slug)
                   .annotate(...)...).filter(...)
    if features_qs.exists():
        filtered_qs = filtered_qs.filter(features_qs)
```

`ListingsQueryParams.feature_slugs: list[str]` (`listings_query.py:44`) has no max-length bound.
The view accepts unbounded repeated query parameters: `search.py:127`
`feature_slugs = params.getlist("features")`.

`src/backend/apps/ads/tests/test_features_filter.py` is the **only** test file for this feature and
uses **one or two** slugs (`:46, :99, :140, :155, :179, :198, :226`). Nothing anywhere in
`src/` tests a large, hostile or repeated `?features=` list.

**Evidence — measured impact (read-only probe, `EXPLAIN` without `ANALYZE`, never executed)**

| `?features=` slugs | JOINs generated | `EXPLAIN` time |
|---|---|---|
| 1 | 5 | 0.13 s |
| 10 | 23 | 0.99 s |
| 50 | 103 | **44.30 s** |
| 100 | 203 | **PostgreSQL backend terminated** |

Two separate probe passes each killed the database server. The container log:

```
LOG:  database system was interrupted; last known up at ...
LOG:  database system was not properly shut down; automatic recovery in progress
LOG:  redo starts at ...
LOG:  redo done
LOG:  database system is ready to accept connections
```

All 22 databases on that instance (including all 17 xdist worker databases) were unavailable for
~30 s. This is the same defect phase 08 filed as **SRCH-001 (CRITICAL)**; this finding is the
*test-coverage and test-hosting* half of it, and adds the planning-time measurement phase 08 did
not take — planning alone, with no `ANALYZE` and no data access, is enough.

**Evidence — why the missing test cannot simply be added**

`src/backend/conftest.py:169-241` already serialises per-worker DDL under
`AdvisoryLockId.TEST_SCHEMA_SETUP`, and the xdist worker databases are correctly separated
(`gw0` … `gw16`). But **nothing in the test settings or the conftest bounds a runaway query**:
`statement_timeout` returns zero hits across `src/` and `docker/` (independently confirmed by
phase 03, whose `DB-004` is the production side of the same gap).

Consequence: adding a hostile-`?features=` test to this suite means one test takes the shared
instance offline and fails the whole run. That is very likely *why* the test was never written.
The fix for the defect and the fix for the missing test are gated on the same change.

**Recommendation**

1. `SET LOCAL statement_timeout` in an autouse fixture for the `src/backend` tree (extend
   `django_db_setup`, or an `autouse=True` fixture wrapping DB tests), set to a few seconds. A
   runaway planning query then raises `statement_timeout` and fails one test instead of the
   cluster. This is test infrastructure, not production code, so it does not touch the
   "production code is king" rule.
2. Once (1) is in place, add the missing test: a hostile-parameter case asserting that a large
   `?features=` list is rejected or capped. Land it together with whatever production fix SRCH-001
   receives, in one commit.
3. A `max_length` on `feature_slugs` in `ListingsQueryParams` is the production-side cap — owned by
   phase 08, not by this phase.

**Effort:** M (fixture + test) for items 1–2; the production cap is phase 08's.

---

### TEST-004 — The immediate-alert `on_commit` ordering is never exercised: the one test that touches it patches `on_commit` to run inline, and there is no rollback-negative test

**Severity:** HIGH
**Rubric item:** (a) — a correctness-relevant transaction boundary is asserted only through a mock.
**Category:** `[BEST-PRACTICE]`
**Confidence:** High — every `on_commit` call site enumerated and its test read.
**Architectural / significant change required:** No.

**Quantified `on_commit` inventory** (`grep on_commit` over `src/` — 4 production call sites):

| Production site | What it defers | Test coverage |
|---|---|---|
| `apps/users/services/deletion.py:63` `bump_search_cache_version` | cache-version bump | **Real.** `test_deletion.py:142+` runs under `django_db(transaction=True)`, so the callback actually fires on commit. |
| `apps/media/signals.py:40` `_cleanup` | physical file deletion | **Real.** `test_ad_image_delete_signal.py` is `django_db(transaction=True)` and asserts the file is gone after commit and still present on rollback. |
| `apps/core/utils/advisory_lock.py:84` (release log) | debug log line | `test_advisory_lock_release_log.py` also patches `on_commit` — but the *lock* release itself is on `conn.commit()`, which is correct; only the log line is stubbed. |
| `apps/moderation/signals.py:72-77` `_deliver` | **Telegram alert delivery** | **Mocked away, and the negative case is absent.** |

**The gap, concretely**

```python
# src/backend/apps/moderation/tests/test_approve_ad_side_effects.py:63, :82
@mock.patch.object(transaction, "on_commit", side_effect=lambda fn: fn())
```

`test_approve_ad_sends_immediate_alerts_when_enabled` and
`..._sends_no_alerts_when_flag_disabled` both replace the deferral mechanism with immediate
execution, so they prove `deliver_immediate_alerts` is *called* when the flag is on and not called
when it is off. They prove nothing about the thing `on_commit` exists to guarantee: that the
message is sent **after** the publish has committed, and **not at all** if it does not.

There is no test anywhere in `src/` in which a publish transaction rolls back and the assertion is
that no alert was delivered. `grep on_commit` in the test tree returns 3 hits, all in the two files
above; none of them constructs a rollback.

**Why it matters beyond tidiness:** `deliver_immediate_alerts` is a real Telegram HTTP call
(`immediate_alerts.py:212, :236` — the same lines phase 06 filed as PII-102). If a future
refactor moved the `on_commit` registration, or a decorator swallowed it, the suite would stay
green while users receive "your ad is published" for ads that were rolled back. The failure is
user-visible and irreversible once the message is sent.

**Related gap, same file family:** `apps/search/services/immediate_alerts.py` has 93 % line
coverage, but `apps/search/tests/test_immediate_alerts.py` is 100 % `pytest.mark.unit` and touches
only `_send_payloads`, `_run_send` and `build_alert_message` — all with `MagicMock` collaborators.
The DB-facing entry point `deliver_immediate_alerts` itself (`immediate_alerts.py:236-262`) is never
exercised against a real database, so its `AlertDelivery` write and `delivered_at` stamp are
unasserted.

**Recommendation**

1. Add a `django_db(transaction=True)` test: publish an ad with the flag on, force a rollback
   inside the surrounding atomic block, assert `deliver_immediate_alerts` was not called. This is a
   single test and it closes the actual risk.
2. Add the symmetric positive: commit, then assert delivery happened *after* the commit (e.g. by
   observing `AlertDelivery` inside an `on_commit` ordering assertion, or simply by relying on the
   fact the test now runs outside a transaction).
3. Remove the `patch.object(transaction, "on_commit", ...)` from `test_approve_ad_side_effects.py`
   once (1) and (2) exist; the patch is what hides the ordering.
4. Add one integration-marked test for `deliver_immediate_alerts` with `_send_payloads` mocked but
   the DB real, so the `AlertDelivery` row and `delivered_at` are asserted.

**Effort:** S

---

### TEST-005 — Two-process consistency is untested: zero tests cross the web/bot boundary in either direction

**Severity:** HIGH
**Rubric item:** HIGH — *"Two-process consistency untested."*
**Category:** `[BEST-PRACTICE]`
**Confidence:** High — exhaustive grep.
**Architectural / significant change required:** **Yes** — this needs a new kind of test (see below).

**Evidence**

The architecture's defining property is that web, bot and scheduler are three processes sharing one
PostgreSQL database. Measured:

* `grep 'from django.test import|Client\(|RequestFactory' src/telegram_bot/**/*.py` — the only
  `django.test` import is `override_settings` (8 hits across `test_ad_create.py`,
  `test_save_photo_integration.py`, `test_support_delivery_email.py`). **No bot test issues a single
  web request.**
* `grep 'telegram_bot\.' src/backend/**/*.py` — **2 hits, both comments**
  (`apps/core/services/translation.py:9`, `apps/core/tests/test_contact.py:24`). **No backend test
  drives a bot handler, dispatcher or middleware.**

What *is* covered, and covered well: the bot FSM is tested against the real shared ORM
(`create_test_ad` re-exported at `src/telegram_bot/tests/conftest.py:109-110`; DRAFT persistence,
`copy_ad`, and the real `submit_ad` are exercised in `test_ad_create.py:495-500`,
`:583-593` and `test_save_photo_integration.py:94,:145,:211,:297`). That is the important half of
the contract and the rubric's *other* HIGH ("bot FSM not tested against the shared ORM") is
**satisfied** — this finding is only about the web side of the boundary.

What is therefore untested:

1. **A bot-published ad is visible and correct on the website.** `test_multi_lang_translation.py:300`
   asserts the ORM sees the row; nothing asserts `/search/?q=…` or `/ads/<id>/` returns it, with the
   right city, price and `category_name` denormalisation.
2. **A web-side state change is observed by the bot.** After `ad_edit` publishes an ad, nothing
   asserts the bot's "my ads" listing or its `AccountStateMiddleware` view reflects it. Given phase
   04's **AUT-002** (session/account-state divergence between web and bot) and phase 06's
   **PII-104** (the alert audience ignoring the same state), a shared predicate regressing in one
   process and not the other would be invisible here.
3. **Scheduler vs. bot vs. web concurrency.** Phase 03's `DB-004` (a blocked `select_for_update`
   stalls every DB op in the bot) and `DB-006`/`DB-007` are all cross-process races. The 23
   `transaction=True` concurrency tests all use *threads inside one process*; none model a second
   process, so none exercises the interleaving that actually occurs (a second connection taking its
   own snapshot, no shared GIL/asgiref serialisation).

**Recommendation**

1. Add a small, explicit cross-process smoke layer rather than a full integration harness: for the
   2–3 highest-value rows (a bot-created PUBLISHED ad, a web-rejected ad, a consent-declined
   seller), assert the outcome from *both* sides. The web side is a `Client` request; the bot side
   is the existing `sync_to_async(ORM)` assertion the suite already uses. Roughly 6–8 tests.
2. For the concurrency dimension, the existing thread-based `transaction=True` tests are the right
   shape and need one addition: a test that opens a *second Django connection* and commits from it
   mid-transaction, to prove the isolation level is `READ COMMITTED` and the first transaction sees
   the change (or provably does not, per the design). This is cheaper than a real second process
   and catches the class of bug that matters.
3. Do **not** try to run the actual bot process inside pytest — the FSM is already covered at the
   service boundary, and a real-process harness would be the over-engineering the project rules
   warn against.

**Effort:** M

---

### TEST-006 — No test covers a NUL byte or other control character in `?q=`; the input-robustness class stops at length, SQL injection and homoglyphs

**Severity:** MEDIUM
**Rubric item:** (a) critical-path coverage
**Category:** `[BEST-PRACTICE]`
**Confidence:** High — reproduced live.
**Architectural / significant change required:** No.

**Evidence — the gap**

`src/backend/apps/search/tests/test_search_view.py:642-712` is the only input-robustness class for
the search view, and it has exactly three cases:

| line | case |
|---|---|
| `:657-671` | oversized query (> 200 chars) → truncated, HTTP 200 |
| `:673-690` | SQL-injection payload → HTTP 200, no error |
| `:692-711` | homoglyph confusable → HTTP 200, no error |

There is no case for control characters. `grep -n 'x00|\\u0000|NUL|null byte'` across
`src/backend/**/*.py` returns **zero** test hits.

**Evidence — the defect, reproduced**

`search.py:66-90` normalises the query with `raw_query.strip().lower()` and truncates to
`MAX_SEARCH_QUERY_LENGTH` (`:75-78`). `str.strip()` removes whitespace, not `\x00`, and the
truncation operates on `len()` characters, so a NUL survives both steps. It is then passed to
`SearchQuery(...)` → `websearch_to_tsquery` and to `increment_popular_search`.

Live result from a read-only probe (FTS trigger installed and verified via `pg_trigger` first, per
the phase-08 method trap):

```
PROBE NUL-in-q -> 500
```

So `GET /search/?q=%00` returns HTTP 500. This is phase 08's NUL-byte finding; what this phase
files is the **coverage gap that let it ship** — a 3-case robustness class that deliberately tests
"hostile input" and happens to omit the one class of hostile input that breaks the database.

**Recommendation**

1. Extend `TestSearchViewInputRobustness` with a parameterised control-character case
   (`%00`, `%0a`, `%1b`) asserting HTTP 200 and zero results, alongside the production fix phase 08
   lands. One test, three parameters.
2. More valuable long-term: turn the class into a `pytest.mark.parametrize` over a small hostile-input
   corpus so the next omitted character is a visible gap rather than a silent one.

**Effort:** S (test) + whatever phase 08's fix costs.

---

### TEST-007 — Nothing tests the `PopularSearch` / `SearchHistory` dedup key under the two-writer model, and the column has no DB constraint

**Severity:** MEDIUM
**Rubric item:** (b)/(a) — the write path that the two-process architecture makes racy
**Category:** `[BEST-PRACTICE]`
**Confidence:** High.
**Architectural / significant change required:** No.

**Evidence**

`src/backend/apps/search/models.py:9-31` — `PopularSearch.query_normalized` is
`models.CharField(max_length=200, db_index=True)` with **no `unique=True` and no
`Meta.constraints`**. The class docstring even states the invariant it does not enforce:
*"one row per normalized query"*.

`src/backend/apps/search/services/popular_search.py:44-52` implements the dedup as a plain
`get_or_create(query_normalized=normalized)`. Under `READ COMMITTED` — which phase 03 confirmed is
the isolation level in use — two concurrent `get_or_create` calls with the same key can both miss
and both insert. Web and bot both write this table from the same `?q=` on `/search/`, so the
concurrency is not hypothetical.

`src/backend/apps/search/services/search_history.py:73-83` has the same shape: `delete()` then
`create()`, with the same window.

**Test coverage measured**

* `apps/search/tests/test_autocomplete.py:288-294` (`test_increment_popular_search_increases_query_count`)
  and `:296-302` (`..._increments_existing`) both run sequentially inside one test transaction. They
  prove the counter increments; they cannot interleave.
* `grep -c 'transaction=True' src/**/tests/*.py` = **23** across the whole suite. None of them is
  in `apps/search/tests/`. The one search test that does touch a shared write path
  (`test_search_cache.py:931`) covers cache-version bumping, not the dedup key.
* There is no `Meta.constraints` introspection test for `PopularSearch` — the pattern
  `test_ad_constraints.py` uses for `Ad` is not applied to it.

**Impact on other phases.** Phase 08 filed the missing `UNIQUE` constraint; the validator confirmed
it produces a `MultipleObjectsReturned` 500. This finding is the test-side reason nothing caught it:
the invariant is asserted only through a single-threaded code path, in the one table whose whole
purpose is concurrent de-duplication.

**Recommendation**

1. Add `UniqueConstraint(fields=["query_normalized"], name=...)` in `Meta` + a migration
   (production change — phase 08's item; this phase does not own it).
2. Add a `test_ad_constraints`-style introspection test asserting the constraint exists in the
   database, so a future `AlterField` cannot silently drop it.
3. Add one `django_db(transaction=True)` test that calls `increment_popular_search` from two threads
   on separate connections with the same query and asserts exactly one row exists. This is the
   direct analogue of the LoginToken claim test phase 03 already has, and it is cheap.

**Effort:** S for items 2–3; item 1 is a migration and is phase 08's.

---

### TEST-008 — `pytest-randomly` reshuffles the suite on every run and the seed is neither pinned nor recorded, so an order-dependent failure is not reproducible

**Severity:** MEDIUM
**Rubric item:** HIGH *"Flaky / non-deterministic tests in CI"* (rubric HIGH band) applied at MEDIUM
because the suite's per-test isolation is sound, so no order dependence has been *observed*; the
risk is latent.
**Category:** `[BEST-PRACTICE]`
**Confidence:** High — plugin presence and active shuffling verified.
**Architectural / significant change required:** No.

**Evidence**

`pytest-randomly 5.0.0` is a declared dev dependency (`pyproject.toml:230`) and is installed and
**active** — it is auto-enabled with no configuration. Shuffling confirmed by the parameter
expansion order within a single class, which is not source order:

```
TestStatusTimestampConstraints::test_bulk_update_to_status_without_timestamp_raises[rejected]
                                                     ...[archived]
                                                     ...[published]
                                                     ...[on_moderation_failed]
TestStatusTimestampConstraints::test_bulk_update_to_status_with_timestamp_succeeds[published]
                                                     ...[on_moderation_failed]
                                                     ...[rejected]
                                                     ...[deleted]
                                                     ...[archived]
```

Meanwhile:

* `pyproject.toml:167` `addopts` sets neither `--randomly-seed` nor `-p no:randomly`.
* `addopts` includes `-q`, and the seed is reported by pytest-randomly in the *preamble* header
  that `-q` suppresses. The baseline run's output contains no seed anywhere.
* `.github/workflows/ci.yml`, `docker/entrypoint-test.sh` and `Makefile.ps1` never pass or record it.

**Impact:** the suite is genuinely shuffled on every run. Today the per-test transaction /
`transaction=True` isolation makes that safe, and the two full-suite runs executed for this audit
both passed 2394/2394 — so this is a *latent* flakiness risk, not an observed one. But when an
order dependence does surface, the CI log will not contain the seed needed to reproduce it, and
attempting to reproduce locally will produce a different order. That is the worst possible
combination: non-deterministic *and* non-reproducible.

**Recommendation**

1. Pin the seed in `addopts` (`--randomly-seed=20260928`) so local, Docker and CI runs are
   reproducible and order dependence becomes a deterministic failure you can debug.
2. Print the seed even in `-q` mode — either drop `-q` in favour of `-ra --no-header`, or add a
   tiny conftest hook that logs `randomly.seed` into the `run` summary.
3. Once (1) is in place, fix any order dependence it exposes. If nothing surfaces, keep the pin
   permanently: a deterministic suite is worth more than the entropy.

**Effort:** S

---

### TEST-009 — `pytest-timeout` and `pytest-rerunfailures` are declared but never configured; a hung test is unbounded in CI

**Severity:** MEDIUM
**Rubric item:** (i) CI gating robustness
**Category:** `[BEST-PRACTICE]`
**Confidence:** High.
**Architectural / significant change required:** No.

**Evidence**

Declared dev dependencies with zero configuration:

* `pyproject.toml:222` `"pytest-timeout>=2.4.0"` — installed. But there is **no `timeout` key** in
  `[tool.pytest.ini_options]` (`pyproject.toml:164-186`), and **no `--timeout`** in
  `.github/workflows/ci.yml:138`, `docker/entrypoint-test.sh:28`, or any `Makefile.ps1` target
  (grep across `*.yml, *.yaml, *.toml, *.cfg, *.ini, *.sh, *.ps1`, `Makefile*` → 0 hits).
* `pyproject.toml:220` `"pytest-rerunfailures>=16.6.1"` — installed, no `--reruns` anywhere (same
  grep, 0 hits).

An unconfigured `pytest-timeout` does nothing: a test that blocks forever blocks the worker
forever, and the 2-hour `timeout-minutes: 30` on the whole job (`.github/workflows/ci.yml:96`) is
the only backstop — by which point the job is simply cancelled with no diagnostic.

This matters more than a generic "add a timeout" recommendation, because unbounded waits are a
demonstrated shape in this codebase: phase 03's **DB-004** measured a 15.05 s unbounded lock wait
in production code, and its validator confirmed `SHOW lock_timeout` and `SHOW statement_timeout`
both return `0` at runtime. The test suite drives that same production code.

Baseline durations for context (`--durations=10`): `test_migration_idempotency` 24.16 s,
`test_makemigrations_check` 7.31 s, the whole fast gate 226 s.

**Recommendation**

1. Add `timeout = 120` (or 300 to leave headroom above the 24 s migration test) to
   `[tool.pytest.ini_options]`, plus `timeout_method = "thread"` so a blocked DB wait is killed
   rather than deadlocking the worker at the GIL.
2. Decide explicitly about `pytest-rerunfailures`: either configure `--reruns 2 --only-rerun
   "flaky"` for the known-shared-DB tests, or drop the dependency. An unconfigured dependency in a
   lockfile is worse than no dependency: it reads as a safety net that is not there.
3. If a timeout does fire, mark the test `@pytest.mark.xfail(reason=...)` rather than raising the
   global number — a growing global timeout hides a growing problem.

**Effort:** S

---

### TEST-010 — 27 `inspect.getsource()` substring assertions make the suite a refactor tripwire with no behavioural value

**Severity:** MEDIUM
**Rubric item:** MEDIUM — *"Tests coupled to implementation details."*
**Category:** `[BEST-PRACTICE]`
**Confidence:** High — enumerated.
**Architectural / significant change required:** No.

**Evidence**

27 occurrences of `inspect.getsource(...)` followed by a substring assertion on the source text,
across 8 files:

| file | count |
|---|---|
| `apps/ads/tests/test_edit_views_locking.py` | 7 |
| `apps/moderation/tests/test_admin_actions.py` | 5 |
| `apps/users/tests/test_admin_pii_containment.py` | 4 |
| `apps/core/tests/test_migrate_locked.py` | 4 |
| `apps/moderation/tests/test_moderation_views.py` | 3 |
| `apps/users/tests/test_unsubscribe.py` | 2 |
| `apps/ads/tests/test_recompute_command.py` | 1 |
| `apps/ads/tests/test_sweep_archive.py` | 1 |

Representative:

```python
# src/backend/apps/moderation/tests/test_admin_actions.py:218-226
def test_bulk_approve_uses_select_for_update_orderby_atomic(self) -> None:
    src = inspect.getsource(moderation_admin_actions)
    assert "select_for_update" in src
    assert "order_by" in src
    assert "atomic" in src
```

This asserts that three substrings appear somewhere in a module's text. It passes identically
whether `bulk_approve` works or is entirely broken, and it fails on a rename or a refactor to an
equivalent construct that changes no behaviour. The suite already runs real `TransactionTestCase`
concurrency tests for the same functions elsewhere, so the signal is duplicated while the
maintenance cost is not.

**The instructive case.** `test_admin_pii_containment.py` is the only test file that specifically
audits the admin surface, and it is built entirely from `getsource` checks on `list_display`
helpers. It passes. It could not have caught **AUT-005 / PII-103** (`UserAdmin` exposes `password`
as a plain-text `CharField`) because that defect lives in the *absence* of `fields`/`fieldsets` —
there is no source text to grep. Phase 04's validator and phase 06's auditor both had to reach for
registered-`ModelAdmin` form introspection instead.

**Recommendation**

1. Replace `getsource` + substring with the observable behaviour the assertion is trying to
   express. For `bulk_approve` that is already covered by real tests; for the migration-lock
   helpers it is the lock behaviour phase 03 verified. Delete the duplicates.
2. For the handful that genuinely assert a *structural* property (e.g. "the sweep runs inside one
   transaction"), use `mock` call assertions on the collaborator rather than text matching.
3. Add the introspection test that this class was reaching for and cannot: for every registered
   `ModelAdmin`, assert the generated form's fields and widgets — a raw identity column or a
   `password` rendered as `AdminTextInputWidget` should fail the suite. This one test would have
   caught AUT-005, PII-103 and would also cover AD-001's unlogged status write. Note phase 06's
   **VAL-007**: scope it to an explicit set of data-subject columns, or it false-positives on
   `SupportContactAdmin.telegram_id`, which is a support *channel* ID.

**Effort:** M (item 3 is the valuable one; items 1–2 are deletions)

---

### TEST-011 — The fast suite builds its schema with `syncdb`, so no test in the 2394 exercises a data migration's effect

**Severity:** MEDIUM
**Rubric item:** (a) — migration/retention correctness
**Category:** `[SPEC-DEVIATION]`
**Confidence:** High.
**Architectural / significant change required:** No.

**Evidence**

`src/backend/config/settings/test.py:89-97`:

```python
class DisableMigrations(dict):
    def __contains__(self, item): return True
    def __getitem__(self, item): return None

MIGRATION_MODULES = DisableMigrations()
```

`conftest.py:169-241` compensates for the two DDL objects that live in migrations rather than in
models (the FTS triggers and exchange rates) by re-applying them per worker. That compensation is
correct and the DB-level CHECK constraints do survive, because `Ad.Meta.constraints` is
model-level and `syncdb` creates it — which is why `test_ad_constraints.py` passes.

What is not exercised: every `RunPython` data migration. The suite's only migration test asserts
*applicability*, not *effect*:

```python
# src/backend/apps/core/tests/test_migrations.py:78-94
def test_migration_idempotency(self) -> None:
    ...
    assert "No migrations to apply" in out2
```

A data migration that silently no-ops — a wrong `apps.get_model`, a filtered-out queryset, a
backfill that matches nothing because the trigger has not run yet — applies cleanly, is
idempotent, and passes. `makemigrations --check` (`test_migrations.py:34-52`) catches *model*
drift only.

This is a real gap for the three backfill migrations in this schema: the search-vector backfills
and the `squash_rehydrate_runsql` step. If one of them is a no-op after a real deployment, no test
in the repository notices — and a reused test database (`--reuse-db`, which is the *default* in
`docker/entrypoint-test.sh:28`) will keep passing because the schema was never built by migrations
in the first place.

**Recommendation**

1. Extend `test_migration_idempotency` to migrate forward into `test_migration_repro`, then assert
   the *state* the migrations are supposed to produce: `Ad.objects.filter(search_vector__isnull=True)`
   is empty, every `AdImage` has its three thumbnail keys, exchange rates are loaded. These are the
   same invariants `_restore_test_schema_post_db_setup` currently re-establishes by hand — moving
   that logic into an assertion closes the loop and makes the hand-written compensation
   self-verifying.
2. Note in `src/backend/conftest.py:169-175` (and in `docs/99-agent/rules.md:56`) that the
   compensation exists *because* migrations are disabled, so a future reader does not treat it as
   redundant.

**Effort:** S

---

### TEST-012 — No test renders or introspects an admin page, so the two largest admin-surface defects shipped through a green suite

**Severity:** MEDIUM
**Rubric item:** (a) critical-path coverage
**Category:** `[BEST-PRACTICE]`
**Confidence:** High — coverage data plus exhaustive grep.
**Architectural / significant change required:** No.

**Evidence — coverage**

From the local coverage run (correct config, CWD `/app`):

| module | coverage | missed lines |
|---|---|---|
| `apps/ads/admin.py` | 57 % | 33, 45-48, 55, 66, 70-71, 77, 79, 92, 116, 120, 126, 128, 141-142, 155, 177, 182, 211-216 |
| `apps/users/admin.py` | 69 % | 17, 19, 21-23, 31, 44-49 |
| `apps/moderation/admin.py` | 57 % | 14, 22-24, 49, 52, 56-58, 74, 77, 80 |
| `apps/analytics/admin.py` | 57 % | 14, 25-26, 40 |

`apps/moderation/admin.py` is the *least* covered admin in the app and is the module whose
`bulk_approve` is dead code (phase 05 VAL-003) — the uncovered lines 14 and 22-24 sit exactly where
the `action_approve` plumbing would be.

**Evidence — no admin-surface test exists**

`grep -n 'get_form\(|get_actions\(|admin.site._registry|UserAdmin|AdAdmin' src/backend/**/tests/*.py`
→ the only hits are the `getsource` checks discussed in TEST-010. Not one test:

* calls `admin.site._registry[Model].get_form(request)` to inspect the generated fields,
* calls `.get_actions(request)` to inspect the wired actions,
* issues a `Client().get("/admin/...")` request, or
* asserts anything about a rendered admin template.

`apps/ads/admin.py:109-114` declares
`actions = [action_reject, action_ban_user, action_soft_delete, action_approve]`, and phase 07's
validator confirmed via introspection that `AdAdmin.get_actions()` really returns all five. Nothing
in the repository asserts that, and nothing asserts the inverse for the models where it matters
(`UserAdmin.withdraw_consent_action` is decorated `@admin.action` but never added to `actions`, per
phase 06's PII-107 — again caught only by external introspection).

**Impact, cross-referenced**

* **AUT-005 / PII-103 (HIGH, merged)** — `UserAdmin` auto-builds a `ModelForm` with `password` as a
  plain-text `CharField`. Reproduced twice by other phases *using introspection*, never by a test.
* **AD-001 (CRITICAL, phase 05)** — `AdAdmin.readonly_fields` omits `status`; a POST to
  `/admin/ads/ad/<id>/change/` with `status=published` published a DRAFT with **zero**
  `ModeratorActionLog` rows. Also found only by external probing.
* **PII-107** — the unwired `withdraw_consent_action`.

Three independently-filed, independently-confirmed defects on the operator surface, none of which
any test in the repository could see.

**Recommendation**

1. Add one test module, `apps/users/tests/test_admin_form_contract.py`, that introspects every
   registered `ModelAdmin` and asserts a declared allow-list of editable fields and widgets.
   This closes AUT-005 and PII-103, and it is the test phase 04's validator asked for when it wrote
   *"any phase owning admin-facing code should introspect registered ModelAdmin form fields, not
   just read admin.py."*
2. Extend it with the inverse assertion for `AdAdmin` — `status` must be in `readonly_fields` or
   absent from the form — which would have caught AD-001.
3. Add a `get_actions()` assertion for each admin that declares actions, so an action is either
   wired or removed (the PII-107 case).
4. Scope rule 1 to an explicit declared set of data-subject columns (phase 06's **VAL-007** warns
   `SupportContactAdmin.telegram_id` is a support *channel* ID and would false-positive).

**Effort:** S for one new module; it has an outsized return because it is a single test that
covers a whole class of admin-surface regressions.

---

### TEST-013 — The `basedpyright` gate is red today, and the bot process is outside both the lint and the typecheck scope

**Severity:** LOW
**Rubric item:** (j) CI gating
**Category:** `[SPEC-DEVIATION]` — **root cause owned by ENT-004 (phase 01); recorded here as the
test-gate view, not as a duplicate.**
**Confidence:** High — measured.
**Architectural / significant change required:** No (CI file only).

**Evidence**

Measured in the repo, exit codes observed:

```
basedpyright .            (from src/backend)      -> 12 errors, exit 1
basedpyright .            (from src/telegram_bot) ->  2 errors, exit 1
ruff check src                                     -> clean, exit 0
```

All 12 errors in the CI scope are in test files (4 in `test_admin_actions.py`, 3 each in
`test_search_view.py` / `test_deletion.py` / `test_incomplete_feature`*, 2 in `test_payment_forms.py`,
1 in `test_moderation_side_effects.py`) — consistent with ENT-004, which phase 01's validator
independently reproduced at exactly 12 errors, 0 in production handlers.

Phase 01 filed this as **ENT-004** and it is theirs to fix; this finding exists only to record the
test-suite consequence:

1. **The gate is red, so it is not gating.** `.github/workflows/ci.yml:158-166` runs
   `uv run basedpyright .` with `working-directory: src/backend`. A red job either blocks every PR
   or gets ignored, and either way it provides no signal. The errors are trivially fixable
   (untyped `advisory_lock` context managers, an incomplete `IncompleteFeature` stub, one
   `# type: ignore` in `test_payment_forms.py`) — worth doing as a standalone hygiene commit
   rather than leaving the whole typecheck gate dark.
2. **The async bot process is not statically analysed at all.** `ruff check` in CI also runs from
   `src/backend` (`:148-156`), so neither tool ever sees `src/telegram_bot`. Phase 10's CQ-002
   rated that gap latent after measuring the bot tree at only 2 type errors (both in tests) — so
   the cost of widening the scope today is near zero, and the benefit is that the process which
   owns the ad FSM, the login-token claim and the contact deep link gets the same treatment as
   the web tier.

**Recommendation**

1. Fix the 12 test-file type errors in a standalone commit so the gate goes green. None of them is
   in production code, so "production code is king" is not engaged.
2. Add a second `basedpyright .` step with `working-directory: src/telegram_bot`, and change the
   ruff step to run from the repository root so `.ai/`, `docker/` and the Makefiles are covered
   too. Both are one-line CI additions; scope them with ENT-004's remediation so they land once.

**Effort:** S

---

## 3. Remediation Order

Ordered by dependency, not by severity. The first three are prerequisites for fixing other
phases' defects.

| # | Action | Owner | Blocks |
|---|---|---|---|
| 1 | **TEST-001 steps 1–3** — change the `create_test_ad` default, migrate the 111 call sites, fix the two docs | this phase | AD-008 fix; phase-05 VAL-003; every later moderation test change |
| 2 | **TEST-013 step 1** — fix the 12 test-file type errors so the typecheck gate is green | this phase + ENT-004 | all CI signal |
| 3 | **TEST-003 step 1** — per-test `statement_timeout` in the backend conftest | this phase | any hostile-parameter test, including the SRCH-001 regression test |
| 4 | **TEST-002** — move the coverage step's `working-directory` to the repo root | this phase | trusting the coverage number at all |
| 5 | **TEST-012** — the admin form/action contract test | this phase | verification of AUT-005, PII-103, AD-001, PII-107 |
| 6 | **TEST-006, 4** — NUL/control-character test, landed with phase 08's fix | this phase + phase 08 | — |
| 7 | **TEST-007 steps 2–3** — constraint introspection + concurrency test, landed with phase 08's `UNIQUE` migration | this phase + phase 08 | — |
| 8 | **TEST-004** — the rollback-negative `on_commit` test | this phase | — |
| 9 | **TEST-011** — assert migration *effects*, not just applicability | this phase | — |
| 10 | **TEST-008, TEST-009** — pin the randomly seed; configure `pytest-timeout`; decide on reruns | this phase | debuggability of everything above |
| 11 | **TEST-005, TEST-010** — cross-process smoke layer; replace `getsource` assertions | this phase | — |

**Rollout hazard (carried from phase 07's VAL-003, applies here too).** Steps 1 and 6–7 are
test-EXPECTATION changes that follow from already-decided production behaviour. They must land in
the same commit as the production change or the branch goes red under pressure and the change gets
reverted. Step 1 in particular must not be split across commits — a half-migrated fixture is
worse than either end state.

---

## 4. What Was Not Audited, and Why

1. **The live `seed` suite (nightly, ~300 s).** Excluded from the fast gate by
   `PYTEST_SKIP_MARKERS=seed`; I ran the fast gate and the coverage variant only. The
   `test_seed.py` (68 tests) and `test_download_seed_photos.py` (59) coverage of the seed generator
   is therefore unmeasured. Effort: it would need a separate ~6-minute run; not blocked by anything.
2. **The live nginx hop.** `mko-bazuna-dev-web-1` and `-bot-1` are crash-looping on a placeholder
   `BOT_TOKEN` in `.env.dev` (CFG-006), so no request was ever issued through the reverse proxy.
   Every HTTP claim in this report comes from Django's test client, which exercises the real
   URLconf, middleware stack and view code but not nginx. Same gap phase 07 declared.
3. **The real-filesystem media paths.** Not run; phase 07 owns that surface and its `VALIDATION`
   is recorded there. My only filesystem interaction was reading a trigger's existence in
   `pg_trigger`.
4. **Concurrency behaviour under genuinely separate OS processes.** My `?features=` probe killed
   the database server twice and a full parallel-process test harness would do the same. The
   `transaction=True` thread-based tests are the only concurrency model I could run safely, so
   TEST-005 item 2 is a recommendation, not a measured gap.
5. **gitleaks / pre-commit secret scanning.** Not installed in this environment; no secret scan was
   run and none is claimed. Test fixtures were classified by value *shape* only (all emails are in
   the reserved `example.com` / `a@b.com` space; all Telegram IDs are in the synthetic
   `7xxxxxx`–`9xxxxxxx` test ranges; `password` values are the literal `"x"`). No `.env.*` value
   was read or quoted anywhere in this report.
6. **Per-test assertion quality inside the 190-test bot middleware suite.** I audited its
   *boundaries* (no cross-process tests, no real network, no forbidden lifecycle transitions,
   `MagicMock` usage of collaborators) but did not read all 36 000 lines. A dedicated test-audit
   phase (`audit-tests-bad-tests`, `audit-tests-full`) exists for that and was explicitly out of
   scope for this run.

---

## Appendix A — Verification Commands

```
# Baseline (fast gate, seed excluded)
docker compose --project-name mko-bazuna-test --env-file .env.test \
  -f docker-compose.yml -f docker-compose.test.yml \
  run --rm --env PYTEST_SKIP_MARKERS=seed test
#   -> 2394 passed, 451 warnings, 226.24s (0:03:46)
#      (-n auto --dist loadgroup --maxprocesses=4)
#      slowest: test_migration_idempotency 24.39s, test_advisory_lock_ids 12.59s,
#               test_prod_logging (x3) ~5.9-7.7s, test_makemigrations_check 7.06s

# Coverage, correct config (CWD /app, i.e. the local path)
... run --rm -e PYTEST_SKIP_MARKERS=seed \
    -e "PYTEST_OPTS=--tb=line -n auto --dist loadgroup --cov --durations=5 --cov-report=term --reuse-db" test
#   -> 2394 passed, 401s; TOTAL 8693 stmts / 1051 missed / 1828 branch / 203 partial / 86%
#      "Required test coverage of 80.0% reached. Total coverage: 85.89%"

# Coverage config discovery, measured from both working directories
docker compose ... run --rm --no-deps -w /app/src/backend --entrypoint "" test \
  /opt/venv/bin/python -c "import coverage;c=coverage.Coverage();cfg=c.config;\
  print(cfg.config_file, cfg.branch, cfg.source, cfg.fail_under, cfg.run_omit)"
#   -> None False None 0.0 []
docker compose ... run --rm --no-deps --entrypoint "" test /opt/venv/bin/python -c "<same>"
#   -> /app/pyproject.toml True ['src/backend', 'src/telegram_bot'] 80.0 [7 patterns]

# Lint / typecheck
uv run ruff check src                     -> clean, exit 0
uv run basedpyright .  (src/backend)      -> 12 errors, exit 1
uv run basedpyright .  (src/telegram_bot) ->  2 errors, exit 1

# FTS trigger presence (phase-08 method trap) - asserted before any FTS-affecting result
SELECT tgname FROM pg_trigger WHERE tgrelid = 'ads'::regclass AND NOT tgisinternal;
#   -> empty for an out-of-tree probe; 'ads_search_vector_update' present after
#      call_command("setup_search_triggers")
```

### Methodology disclosure — one contaminated run

A first coverage run reported `6 failed, 2361 passed, 27 errors in 437 s`. That run is **not** a
product defect and is **not** used as evidence anywhere in this report. The cause was mine: I
launched a second, identical container against the same `test_mko_bazuna` with `--reuse-db` while
the first was still running — precisely the collision phase 06's validator recorded as **VAL-010**.
The serial re-run passed 2394/2394 and is the baseline quoted throughout. I report it because
VAL-010 is a live hazard for parallel validators, and because a reader comparing logs should know
why a red run is in the transcript.

### Cleanup performed

Probe scripts under `.ai/tmp/` (`probe_nul_and_features.py`, `tmp_astcount1.py`,
`tmp_astcount2.py`, `cov_ci_style.txt`, one `__pycache__` entry) were created by me and have been
deleted; files belonging to the concurrently-running phase 13 (`perf13/`, `explain_probe*.py`,
`p2..p9.txt`, `run_probe.ps1`, `seed_scale.py`, `cities_shape.py`) and phase 09
(`validate09_probe*.pyc`) were left untouched. `git status --porcelain` reports **no modified
tracked file**. No scratch database was created — every probe ran in pytest-django's own
`test_mko_bazuna`. The phantom `mko_bazuna` database was re-verified untouched after the crashes:
**39 tables, `to_regclass('django_migrations') IS NULL`**. The instance was left healthy
(`SELECT 'db ok'` → `db ok`) and no container was left running.

---

## Appendix B — Methodology Passes (not findings)

`problems_only = TRUE` means these are recorded, not reported as defects. They are listed because
a reader deciding how much weight to put on the findings above needs to know what was checked and
found sound.

1. **Forbidden external calls — clean.** `pytest-socket` is *correctly* absent: the suite is
   supposed to exercise real HTTP clients. No test reaches a real network: every external client
   is mocked or a `respx`/`httpx` transport double. `grep -n 'requests.get\(|urlopen\(|httpx.get\('
   src/**/tests/*.py` returns no live call.
2. **No database-outside-Django calls — clean.** No raw `psycopg.connect` in tests; the 23
   `transaction=True` concurrency tests use the ORM and `threading`, which is correct.
3. **Forbidden lifecycle transitions — clean.** `AdStatus` transitions are guarded by DB-level
   CHECK constraints and `test_ad_constraints.py` verifies each one against the real database
   (16 tests: mutual-exclusivity, `status`/`published_at` consistency, bulk-update timestamp
   guards). This is exactly the "would the suite catch it" question, and here the answer is yes.
4. **Contact gating — genuinely well covered.** `apps/core/tests/test_contact.py` blocks each
   condition independently (banned, not approved, ads_auto_publish off, moderation_failed
   category, bad exchange rate, missing consent) and `test_contact_gate.py` in the bot tree proves
   both processes delegate to the same `_check_seller_contactable` helper. Phase 10's PASS
   ("contact gating genuinely shared") is corroborated here.
5. **FTS visibility — covered at the view level.** `test_search_view.py:123`
   (`test_search_with_query_returns_only_published`) creates a PUBLISHED and a DRAFT ad and asserts
   only the PUBLISHED one is returned by `/search/`. `test_search_triggers.py` covers the trigger's
   Russian/Serbian vector recomputation and the trigger-presence guard
   (`test_trigger_exists_and_is_enabled`). Note the trap I hit: these tests pass *because*
   `src/backend/conftest.py:169-241` re-installs the trigger per worker — an out-of-tree probe does
   not get that fixture and silently reports "0 hits".
6. **Sensitive-data fixtures — clean.** Every email literal in the test tree is in the reserved
   `example.com` / `b.com` space; every Telegram ID is in the synthetic `7xxxxxx`–`9xxxxxxx` test
   ranges; `password` values are the literal `"x"`. No `.env.*` value was read or quoted.
7. **Test independence — clean.** 106 `pytest.mark.django_db` (transactional) and 23
   `transaction=True`; no `TestCase` subclass, no shared class-level mutable state that survives a
   rollback. The session-scoped fixtures (`seller`, `user`, `category`, `city`, `admins`) are all
   `get_or_create`/idempotent, which is why they are safe to share across the whole session
   (introduced in commit `700d99d`).
8. **External-API degradation — covered.** `translation.py` sits at 93 % line coverage; the retry /
   circuit-breaker / graceful-fallback branches are exercised, and
   `test_search_translation_outage.py` locks in the degradation contract. This is the rubric's
   "LLM/external API fallback" dimension and it is **satisfied**.
9. **Migration consistency — partially covered, and correctly reasoned.** `test_makemigrations_check`
   detects model drift and `test_migration_idempotency` detects a non-idempotent migration. The gap
   is the *effect* of data migrations (TEST-011), not the detection of schema drift.
10. **`MagicMock` discipline — acceptable at boundaries.** ~600 mock-assertion lines across the
    suite, concentrated where they belong: Telegram HTTP, cache, advisory locks, and the
    `deliver_immediate_alerts` HTTP call. Mocking *HTTP* is not mocking the unit under test. The
    cases where a mock removes the property being asserted are TEST-001 and TEST-004.
