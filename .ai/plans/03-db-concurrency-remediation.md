---
plan_id: "03-db-concurrency-remediation"
phase: "03"
phase_name: "Database & Concurrency Consistency"
source_report: ".ai/audit/99-validation/03-db-concurrency-validated-findings.md"
source_findings: ".ai/audit/03-db-concurrency/findings.md"
date: "2026-09-29"
planner: "Planner (subagent)"
anchor_commit: "4fd8bd0"
report_anchor_commit: "9e96b84"
status: "planned"
findings_in_scope: 15
findings_implemented: 10
findings_rejected: 1
findings_constrained: 3
findings_cross_cutting: 1
blocks: 11
---

# Execution Plan — Phase 03 Remediation (Database & Concurrency Consistency)

## 0. Header, provenance and scope statement

### 0.1 Provenance

| Item | Value |
|---|---|
| Source report | `.ai/audit/99-validation/03-db-concurrency-validated-findings.md` (validated, 952 lines) |
| Source findings file | `.ai/audit/03-db-concurrency/findings.md` — **deleted from the working tree** (tracked deletion, see §1). Recorded for traceability only; **not** an input. |
| Report anchor commit | `9e96b84` |
| Code-context document | `.ai/tmp/code-context-phase03.md` (1313 lines, Auditor) |
| **Working anchor commit for this plan** | **`4fd8bd0`** (`git rev-parse --short HEAD`) |
| Date | 2026-09-29 |
| Findings in scope | 11 (`DB-001` … `DB-011`) + 4 `VAL-001` … `VAL-004` = **15** |
| Verdicts in source report | Confirmed 6 · Adjusted 4 · Rejected 1 |
| Validated severity split | 0 CRITICAL · 3 HIGH (`DB-002`, `DB-003`, `DB-004`) · 3 MEDIUM (`DB-005`, `DB-007`, `DB-008`) · 3 LOW (`DB-009`, `DB-010`, `DB-011`) |
| State at the anchor | 0 fully fixed · **1 partially fixed** (`DB-004`) · 9 open · 1 rejected (`DB-006`) |
| Execution blocks | 11 |
| Implementor concurrency | 1, strictly sequential (project rule: only one implementor at a time) |

**Naming convention used by this plan.** This plan cites its own items with the
**cycle-scoped prefix `03-DB-00N` / `03-VAL-00N`**, and §0.5 (Q14) records that decision
for phases 04–15. The precedent is already in the tree:
`src/telegram_bot/tests/test_unsubscribe.py` cites `03-DB-002`. Bare `DB-00N` in this
document therefore always means "a *previous* cycle's* defect id that collides with this
cycle's namespace" unless explicitly marked.

---

### 0.2 Evidence basis — read this before executing any block

Two inputs, and they do not fully agree with each other or with the tree. **The tree at
`4fd8bd0` is the authority.** Where they disagree, the disagreement is recorded here.

#### 0.2.1 What the Planner re-verified directly in the tree at `4fd8bd0`

| Claim | Verification |
|---|---|
| `DB-001` open | `create_draft_ad`'s inner `_create()` still wraps `Ad.objects.create(...)` in the **outermost** `transaction.atomic()`; the `except IntegrityError` handler's first statement is `Ad.objects.filter(...).delete()` against an already-aborted transaction. `src/telegram_bot/services/ad_data/orm.py`, `create_draft_ad`. |
| `DB-002` open | `record_event` is still a bare `try: AnalyticsEvent.objects.create(...) / except Exception:` with **no** `atomic()` and **no** `SET CONSTRAINTS`. `src/backend/apps/core/services/analytics.py`. The module docstring still asserts "performs NO `transaction.atomic()` so it remains transparent to the caller's transaction boundary". |
| `DB-003` open | `sweep_drafts.Command.handle` still filters `status=AdStatus.DRAFT, created_at__lt=cutoff_date` with a 30-minute cutoff. `Ad.Meta.indexes` still declares `IX_ads_draft_sweep` on `fields=["status", "created_at"], condition=Q(status=AdStatus.DRAFT)`. No bot heartbeat exists. |
| `DB-004` **partially** fixed | Repo-wide search for `lock_timeout|statement_timeout|idle_in_transaction_session_timeout` over `src/` and `docker/` returns **zero matches**. `src/backend/config/settings/base.py` sets neither. **Both** `ENT-006` addendum elements are already shipped: `migrate_locked`'s module docstring now says a contending run *blocks*, and `advisory_lock`'s session branch logs `"Requesting session advisory lock %s"` before `pg_advisory_lock`. |
| `DB-005` open | `submit_ad` still calls `move_staging_to_permanent(input.photos)` **before** `with transaction.atomic():`. `sweep_orphaned_media` still snapshots (`_collect_referenced_keys`) → walks (`_walk_media_files`) → unlinks, with `_SEED_SUBDIR = "seed"` and `STAGING_SUBDIR` as the only exclusions, all inside one `atomic()` + `advisory_lock(SWEEP_ORPHANED_MEDIA)`. |
| `DB-006` rejected | Carried forward as rejected. Nothing to implement. |
| `DB-007` open | `deliver_immediate_alerts` takes no advisory lock, opens no transaction, and calls `record_notifications(saved_search, [ad])` **before** `_executor.submit(_run_send, payloads)`. `record_notifications` returns `len(ads)` ("not necessarily created" — the docstring says so). `find_matching_saved_searches` has **no** `NOT EXISTS` filter. `IMMEDIATE_ALERTS_ENABLED` defaults to `False`. |
| `DB-008` open | `archive_sweep.Command.handle` still wraps the entire sweep in one `transaction.atomic()` around `advisory_lock(ARCHIVE_SWEEP)`, iterating a single `select_for_update().order_by("pk")` queryset. `recompute_normalized_prices.Command.handle` wraps `_recompute` in one `atomic()`; `_recompute` iterates `.values_list("pk", flat=True).iterator(chunk_size=_BATCH_SIZE)` and calls `_process_batch` (which does `select_for_update().filter(pk__in=...)` then `bulk_update`) per 500-row batch — all inside the one transaction. |
| `DB-009` open | `copy_ad` builds `Ad(...)` with **no explicit `status=`** (relying on the model default `DRAFT`), never handles `uq_ads_single_draft_per_user`, and never touches an existing DRAFT. The only production caller is `src/telegram_bot/handlers/ad_copy.py::cmd_copy`, which answers `_("Failed to copy ad: {error}").format(error=e)` — the raw psycopg `IntegrityError` text interpolated into a user-facing message. |
| `DB-010` open | `advisory_lock`'s transaction branch still registers the release message via `transaction.on_commit(...)` after `pg_advisory_xact_lock`. The session branch already uses `try/finally` and is the model to copy. |
| `DB-011` open | All six commands still build `storage_keys` inside the `atomic()` + lock block and consume it only through `len(storage_keys)` in the closing `logger.info`. The misleading collection-site comment is present in each. |
| Migration numbering | `ads` → `0001`…`0007_adimage_ix_adimages_image_and_more`, next is **`0008_*`**. `search` → `0001_initial`, `0002_redact_search_queries`, next is **`0003_*`**. `core` → …`0005_scheduler_daily_state`, next is **`0006_*`**. `media` → `0001_initial`, next is **`0002_*`**. |
| `AdvisoryLockId` | 18 members in `src/backend/apps/core/enums.py`, IDs 1–9, 11, 12, 100–104, 110, 111. ID 10 reserved. **Phase 03 allocates none** (see §5.3). |
| `docs/02-database/db-retention.md` | Still states verbatim: *"Acquires advisory lock 11; a contending run **blocks** until the lock is granted (**no lock timeout is configured**)."* and *"All retention values are hardcoded… No environment variables or CLI arguments (beyond `--dry-run`) are read for retention durations."* `docs/02-database/db-indexes.md` still documents `IX_ads_draft_sweep` on `["status", "created_at"]`. |
| Baseline static gates | `uv run ruff check src/` and `uv run basedpyright src/` are **green** at `4fd8bd0` (re-confirmed by the Auditor; phase 01's `ENT-004` fixed the gate scope to `src/`). |

#### 0.2.2 Report statements the **tree contradicts** — corrections, not re-openings

| # | Report / context statement | What the tree shows | Where this plan acts |
|---|---|---|---|
| C-1 | `03-DB-004`'s Impact lists `submit_ad`, `handle_login_orm`, `ad_edit`, `ad_archive`, `ad_reactivate` as the row-lock waiters that stall *the bot*. | `ad_edit`, `ad_archive`, `ad_reactivate` are **Django web views** in `src/backend/apps/ads/views/edit.py` (module-level `@login_required` / `@require_POST` functions that `get_object_or_404(Ad.objects.select_for_update(), …)`). There is **no** bot handler by any of those names. The genuine **bot-side** waiters are `submit_ad` (`apps/ads/services/submission.py`), `handle_login_orm` (`telegram_bot/handlers/login.py`), and the `SavedSearch.objects.select_for_update()` in `telegram_bot/handlers/alerts.py`. | BLOCK 5's scope is split into a bot-side and a web-side surface; the web side is bounded only by `gunicorn.conf.py`'s `timeout = 60`. |
| C-2 | `CONN_HEALTH_CHECKS` is "configured". | `CONN_HEALTH_CHECKS` is **set nowhere in the repository**. The effective `CONN_MAX_AGE = 0` comes from Django's global default — `django-environ` 0.14.0's `db_url_config()` never emits `CONN_MAX_AGE`. | Correct behaviour, different mechanism. §6 forbids reopening `CONN_MAX_AGE` (it is phase-01 `ENT-010` Half B, **rejected as intentional design**). |
| C-3 | The `DATABASES["default"]` discrete-`POSTGRES_*` branch that names `"CONN_MAX_AGE": 0` is a live configuration path. | `docker-compose.yml` injects `DATABASE_URL` into **every** service (migrate, load_catalog, scheduler, seed, web, bot), so the **first** branch (`env.db()`) always runs. The discrete branch is **dead in deployment**. Note also: the first branch does `DATABASES["default"]["OPTIONS"] = {"prepare_threshold": None}`, i.e. it **replaces** `OPTIONS` wholesale. | BLOCK 5 must add any new `OPTIONS` key to **both** branches even though one is dead, and must not rely on a `?options=-c …` parameter in `DATABASE_URL`. |
| C-4 | `record_event` has "12 call sites". | **9 call expressions across 6 modules**, of which 4 sit inside a caller-owned transaction: `auto_moderation._fail_moderation` and `._pass_moderation` (each own `atomic()` nested inside `submit_ad`'s outer `atomic()` ⇒ **savepoint**, not a plain block), and `handle_login_orm` (outer `atomic()`, but the `record_event` call sits **after** the savepoint block closes ⇒ **no savepoint**). The other five are autocommit. | BLOCK 3's call-graph table uses these figures. The narrower count makes the *reachability* argument harder, not easier — recorded in §7. |
| C-5 | `DB-001`'s recommended in-repo precedent is `login.handle_login_orm:226-240`. | Phase 01 `ENT-005` (commit `aa71faa` + `cc54f8f`) extracted `src/backend/apps/users/services/login_token.py` and rewrote `login.py`. The line reference is stale; the **pattern** (a nested `atomic()` savepoint around `User.objects.get_or_create` whose `except IntegrityError` branch runs a plain query) must be re-located by symbol before being copied. | BLOCK 4's Auditor task. **Never cite a line number as a task target** — cite the symbol. |
| C-6 | `DB-008`'s evidence cites `scheduler.py`'s hourly list as covering `recompute_normalized_prices`. | `HOURLY_COMMANDS` and `DAILY_COMMANDS` in `src/backend/apps/core/utils/scheduler.py` contain **neither** `recompute_normalized_prices`. It is operator-triggered only; `archive_sweep` is the hourly exposure. | Already corrected in the validated report. BLOCK 7 records it so the block's risk rating reflects the real cadence. |

#### 0.2.3 **Planner finding, not in the report or the code context** — a binding constraint on DB-002

`src/backend/apps/ads/tests/test_ad_detail_queries.py` is an **N+1 regression guard** that
renders a real ad-detail page inside `CaptureQueriesContext` and asserts
`len(ctx.captured_queries) <= _QUERY_BOUND` with `_QUERY_BOUND = 16`. Its comment
enumerates the budget **explicitly, line by line**, and one of the enumerated lines is:

```
#   1 INSERT (AnalyticsEvent)
```

`src/backend/apps/core/services/analytics.py`'s own `record_event` docstring cites the
same constant: *"The single INSERT is the only query issued on the success path, keeping
the ad-detail render budget (see `test_ad_detail_queries._QUERY_BOUND`) within scope."*

**Consequence.** DB-002's recommended Option 1 — wrap the INSERT in a nested
`transaction.atomic()` **and** issue `SET CONSTRAINTS ALL IMMEDIATE` inside that
savepoint — adds transaction-control statements on the `AD_VIEWED` path, which runs in
**autocommit** (`apps/ads/views/listings.py`). Whether Django's `CaptureQueriesContext`
counts those statements is **not established here**; the implementor must measure it in
the same change and, if the count grows, either raise `_QUERY_BOUND` with a stated
derivation or choose the option that does not add statements.

**Neither the validated report nor the code context mentions this.** It is recorded here
as a **binding constraint** on BLOCK 3 (see BLOCK 3, "Binding constraints") and in §7.
It is *not* a reason to pre-empt DB-002's open design question; it is a reason to make
that question explicit.

#### 0.2.4 Claims the plan does **not** treat as proven

The following were runtime claims in the source report's `V-01`…`V-11` evidence and were
**not re-derived** during the audit pass and are **not** re-derived by this plan. The
static absence of the configuration is the load-bearing fact; the runtime values are not:

- `SHOW lock_timeout` / `SHOW statement_timeout` returning `0` (the **static** absence of
  any setting anywhere in `src/` or `docker/` *is* verified above).
- The 3 s hold / 3.01 s blocked-wait transcript.
- `InternalError` (not `TransactionManagementError`) being the exception raised by
  DB-001's dead recovery branch. The **Django mechanism** is unambiguous — `needs_rollback`
  is set only when an exception propagates *through* a block, and here it is caught inside
  it — but the exact class is a runtime detail.
- `SET CONSTRAINTS ALL IMMEDIATE` inside a savepoint actually rescuing the caller's write
  (report `V-06`). **This is the single load-bearing runtime premise of BLOCK 3.** BLOCK 3's
  first action is to reproduce it in the Docker test database and **not** proceed on the
  report's word alone.
- `analytics_events`' FKs being `DEFERRABLE INITIALLY DEFERRED` (report `V-01`) and the two
  generated constraint names.
- `QuerySet.delete()` re-evaluating the sweep filter at DELETE time (report `V-07`) — the
  basis of the DB-006 rejection. DB-006 stays rejected; this is recorded only so a future
  Django-floor change re-opens it knowingly.
- The wall-clock duration of `os.walk(MEDIA_ROOT)` on a real media volume (DB-005's exposure
  window), and whether a second bot process exists in any deployment (DB-001's
  reachability argument).

**The tree wins.** If any statement in this plan conflicts with the tree at `4fd8bd0`,
the tree is correct and the implementor must re-read before writing code.

---

### 0.3 Scope statement (explicit)

**In scope — implemented by this plan (10):**
`DB-001`, `DB-002`, `DB-003`, `DB-004` (**timeout half only**), `DB-005`, `DB-007`,
`DB-008`, `DB-009`, `DB-010`, `DB-011`.

**Rejected — no work item (1):**

- **`DB-006`** — rejected by the validator; the stated mechanism (`QuerySet.delete()`
  filtering on primary key only) is factually wrong for a non-fast-deletable model. The
  residue (a logged count that can disagree with the delete count, and the redundant
  pre-delete scan) is **already covered by `DB-011`**. Re-examine only if the Django floor
  moves outside `>=5.2.16,<6.0`.

**Landed as binding constraints, not as separate code (3):**

- **`03-VAL-001`** → its *tracker* half is **DECIDED** (§0.5, Q14): this plan and every
  later phase key on `NN-<PREFIX>-00N`. Its *source-comment* half is **BLOCK 11**, gated.
- **`03-VAL-002`** → the ordering edge `DB-002 → DB-004`. Both blocks ship; the order is
  load-bearing, not cosmetic. Enforced by `depends_on` in BLOCK 5.
- **`03-VAL-003`** → `AD-005` (phase 05, HIGH) and `03-DB-001` (this cycle, MEDIUM) are
  **one defect filed twice with disagreeing severities**. This plan ships **one** work item
  at **MEDIUM** and **escalates the re-rating to the coordinator**. BLOCK 4 is gated on
  that acknowledgement.
- **`03-VAL-004`** → two of the audit input's runtime reproductions do not survive contact
  with the production code path (§0.2.4). **Documentation-only**, routed to the
  coordinator for the final report (§5.5). No code.

**Cross-cutting (1):**

- **`03-VAL-001`** → BLOCK 11. The finding-ID namespace is ambiguous in **68 shipped
  locations across 26 files** and this cycle's IDs are *already* cited in two production
  files. Recorded in §5.2 for phases 04–15.

**Counts:** 10 implemented + 1 rejected + 3 constrained + 1 cross-cutting = **15**.

---

### 0.4 Severity corrections

The source report's `Severity movement` line reads
`0 CRITICAL · 3 HIGH · 3 MEDIUM · 3 LOW = 9 open`, which **matches** its per-finding
verdicts. **No tally correction is required.** It is recorded here so a reader does not go
looking for a phase-03 equivalent of phase 01's `VAL-005` and not find one — and so the
per-finding column is treated as authoritative by default.

| Severity | Findings |
|---|---|
| CRITICAL | — (0) |
| HIGH | `03-DB-002`, `03-DB-003`, `03-DB-004` (3) |
| MEDIUM | `03-DB-005`, `03-DB-007`, `03-DB-008` (3) |
| LOW | `03-DB-009`, `03-DB-010`, `03-DB-011` (3) |
| rejected | `03-DB-006` |

**One severity is a coordinator decision, not this plan's:** `AD-005` (phase 05) is filed
**HIGH** for the same defect this plan rates **MEDIUM** (`03-VAL-003`). BLOCK 4 ships the
single work item at MEDIUM; the phase-05 re-rating is escalated, not silently ignored.

---

### 0.5 Open technical questions — resolved here, or explicitly gated in their block

The code-context document raises **14** questions. **Nothing below is left silently
ambiguous.** Each is either DECIDED in this plan (with the reasoning stated) or carries a
named *decision gate* inside its block with the options and their consequences recorded.
**This plan does not choose on any question where the code context flagged real technical
uncertainty.**

| # | Question | Disposition | Owner |
|---|---|---|---|
| **Q1** | Global `DATABASES[...]["OPTIONS"]` timeout vs. per-transaction `SET LOCAL`? | **OPEN — decision gate in BLOCK 5.** See §3.5.1 for the full trade-off table and the six shipped concurrency tests that constrain the answer. | Researcher + Planner, BLOCK 5 |
| **Q2** | Where does the bounded-retry `OperationalError` boundary live, and who owns the seller-facing message? | **OPEN — decision gate in BLOCK 5.** The full `select_for_update` call-site inventory must be enumerated and split retry-vs-error before any code is written. | Researcher + Planner, BLOCK 5 |
| **Q3** | `SET CONSTRAINTS ALL IMMEDIATE` or a named constraint? | **OPEN — decision gate in BLOCK 3.** `ALL` also re-validates the *caller's* other pending deferred constraints at the analytics-INSERT point. The two generated FK constraint names must be **read from the live schema in the Docker test database**, not assumed. | Researcher + Implementor, BLOCK 3 |
| **Q4** | DB-002 Option 1 (savepoint + `SET CONSTRAINTS`) or Option 2 (`on_commit` / call after the `atomic()`)? | **OPEN — decision gate in BLOCK 3.** The two options have **different costs against shipped tests**: Option 2 *inverts* `test_record_event_inside_commit_persisted` and `test_record_event_inside_rollback_not_persisted`. Both encodings must be stated before choosing. | Planner + Researcher, BLOCK 3 |
| **Q5** | DB-003 heartbeat: explicit per-handler call or a new aiogram middleware? | **OPEN — decision gate in BLOCK 6.** ~10 FSM handlers write `state.update_data(...)`; a middleware is one touch point but new cross-cutting machinery in a package that currently has four middlewares. | Researcher + Planner, BLOCK 6 |
| **Q6** | Does the heartbeat also need to protect `staging/` files, and does `_STAGING_TTL_SECONDS` need re-deriving? | **OPEN — decision gate in BLOCK 6.** With an `updated_at` heartbeat a dialog can span arbitrarily long, so a photo uploaded at step 1 can be reaped at step 9. Must be quantified before the predicate flips. | Researcher, BLOCK 6 |
| **Q7** | DB-005: **where does the final media move happen relative to the transaction boundary?** | **OPEN — decision gate in BLOCK 8. The single largest design question in the phase.** Phase 01's plan explicitly deferred it to phase 03 and nothing in the tree pre-empts it. Options and their consequences in §3.8.1. | Researcher + Planner, BLOCK 8 |
| **Q8** | DB-005: is the cheaper re-check-before-unlink variant actually safe? | **OPEN — bundled into BLOCK 8's gate.** It narrows but does not close the window, and costs a transaction per candidate orphan inside a lock already held for the whole `os.walk`. | Researcher + Planner, BLOCK 8 |
| **Q9** | DB-007: does the shared advisory lock close the double-send, or is `find_matching_saved_searches`' missing `NOT EXISTS` the real hole? | **OPEN — decision gate in BLOCK 9.** §2.7 of the code context shows `record_notifications` returns `len(ads)`, not the created count, and the immediate matcher has **no** `NOT EXISTS` filter. **Adding the lock alone is provably insufficient.** | Researcher + Planner, BLOCK 9 |
| **Q10** | DB-007's delivery-state column: which states, who writes them, when, and what is the backfill? | **OPEN — decision gate in BLOCK 9.** `send_alerts.Command.handle`'s shipped docstring already nominates "a delivery-state column on `SavedSearchNotification` (phase 03 `DB-007`'s schema)" — the direction the tree points at, not a decision this plan may pre-empt. | Planner, BLOCK 9 |
| **Q11** | DB-008: how is "lock held once across per-batch commits" achieved, given `pg_advisory_xact_lock` releases with the enclosing transaction? | **OPEN — decision gate in BLOCK 7. Structurally unresolvable as written.** `advisory_lock(session=False)` *requires* an enclosing `atomic()`; `pg_advisory_xact_lock` releases at the end of the *enclosing* transaction, so an outer `atomic()` spanning the loop makes the per-batch commits not real commits. And `test_sweep_lock_structure.py` asserts `session is False` for both commands. | Researcher + Planner, BLOCK 7 |
| **Q12** | DB-009: which product rule — "a new draft replaces the current one" or "a second draft is rejected with a message"? | **OPEN — decision gate in BLOCK 10. This is a product decision, not an implementor's.** The two choices produce different seller-visible behaviour and different i18n strings, and the report explicitly recommends a single rule applied in **both** creators. | User/product, via coordinator, BLOCK 10 |
| **Q13** | `03-VAL-003`: `AD-005` vs `03-DB-001` severity. | **DECIDED (partially).** One work item, one severity: **MEDIUM**, shipped in BLOCK 4. The **re-rating of phase 05's `AD-005` is escalated to the coordinator** (§5.4). BLOCK 4 is gated on that acknowledgement, not on a new investigation. | Coordinator |
| **Q14** | Cross-cutting: how does this cycle's tracker key its IDs, and are the ~68 shipped comments disambiguated? | **DECIDED (tracker) / OPEN (source).** *Tracker:* cycle-scoped prefix `03-DB-00N` / `03-VAL-00N`, adopted by this plan and recorded in §5.2 for phases 04–15. The precedent already exists in `src/telegram_bot/tests/test_unsubscribe.py` (`03-DB-002`). *Source comments:* the ~68 legacy citations are **BLOCK 11**, gated on a coordinator decision — see §3.11.1 for the three options. | Coordinator (gates BLOCK 11); DECIDED for all new phase-03 comments |

---

## 1. Environment and command contract for the implementor

These constraints bind **every** block. They are not optional and they are not re-derived
per block.

| Concern | Rule |
|---|---|
| **Test execution** | **Docker only.** `.\Makefile.ps1 test` (Windows PowerShell 7+) or `make test`. **Never `uv run pytest` locally** — there is no database on `localhost:5432`. |
| **Test DB** | Start once per session: `.\Makefile.ps1 test-db` (starts `mko-bazuna-test-db-*`). |
| **Targeted test run** | `$dc run --rm -e PYTEST_OPTS="<tokens>" test` with `$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'`. `--env-file .env.test` is **required** (compose interpolates `${POSTGRES_*?}` from it). Use `$TestProject = "mko-bazuna-test"`, **never** `mko-bazuna-dev`. |
| **`PYTEST_OPTS`** | **Word-split on spaces and unquoted.** `-k test_name` and bare file paths work; a quoted multi-token value such as `-k "a b"` does **not**. Setting `PYTEST_OPTS` **replaces** the defaults (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`), so a targeted run loses xdist parallelism and DB reuse. Prefer marker exclusion via `PYTEST_SKIP_MARKERS` over `PYTEST_OPTS`. |
| **`PYTEST_SKIP_MARKERS`** | `--env PYTEST_SKIP_MARKERS=seed` skips the nightly seed suite. **This is the default gate for every block in this plan**; no block touches seeding or image generation. |
| **Fresh schema** | `.\Makefile.ps1 test-recreate` after **any** migration change and after an interrupted run. **Required after BLOCK 6 (`ads/0008_*`), BLOCK 8 (if it adds `media/0002_*`) and BLOCK 9 (`search/0003_*`).** |
| **Live database inspection** | BLOCK 3 and BLOCK 5 must confirm runtime facts (the generated FK constraint names; whether `SET CONSTRAINTS` rescues the caller's write). Do it against the **test** database via the test service — e.g. `$dc exec db psql -U <user> -d test_mko_bazuna -c "..."` — never against an operator database. Never `DROP` anything outside the test stack. |
| **Image rebuild** | Not needed — the `test` service bind-mounts the repository. |
| **Static gates** | `uv run ruff check src/` and `uv run basedpyright src/` run on the host (no DB needed). **Both are green at `4fd8bd0`** — they must stay green. The CI scope is `src/`, not `.` (phase 01 `ENT-004`). |
| **`ruff` autofix** | `uv run ruff check --fix src/` sorts imports (`I001`). `ruff format` is **not** the project convention. |
| **Never** | `--override-ini=addopts=` — it strips `--import-mode=importlib`, which `pyproject.toml` sets and the suite depends on. |
| **i18n** | Every **user-visible** string wrapped in `{% trans %}` / `gettext` **and** with a **non-empty** `msgstr` for `ru` **and** `bs` (`en` may be empty). Blocks 6 and 10 add user-visible strings. `test_i18n_completeness.py` / `test_i18n_pipeline.py` gate it. Note `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` is a **shared artefact** — see §5.3. |
| **`print()`** | Forbidden. `logger = logging.getLogger(__name__)` with lazy `%s` formatting. All comments, docstrings, log messages, error messages and documentation in **English**. |
| **Typing** | `# pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped` is the project's established, greppable inline suppression and is required on every `with transaction.atomic():` line. Never use a suppression where a typed signature or an explicit `assert` is the honest fix. |
| **`StrEnum` / `IntEnum`** | Every fixed value is an enum member, never a bare string or a dict-of-strings. This includes the DB-004 timeout value (if it is a named constant) and any DB-007 delivery-state value. |
| **Task targets** | **Never a line number.** Targets are `file` + `type` (`class` / `function` / `method` / `module`) + `name`. Line numbers may appear in evidence prose; they may **never** be a task target. |
| **Pydantic v2** | Only at system boundaries (bot input DTOs, settings schemas). The Django ORM remains the persistence layer for all CRUD in this plan. |
| **Service boundaries** | New business logic goes in a `services/` package, never in a view or a handler. Bot → backend only; `apps.*` must **never** import `telegram_bot.*`. |
| **Bot async** | Every bot DB call is `@sync_to_async` at the default `thread_sensitive=True`. **Do not** "fix" DB-004 by raising the asgiref worker count — `thread_sensitive` exists so a transaction and its connection stay on one thread. |
| **TX-then-FS** | Filesystem side effects happen only **after** commit, via `transaction.on_commit()`. Never unlink or move inside `transaction.atomic()`. |
| **Dirty tree** | **Hard rule.** The working tree is dirty **by design** and demonstrably changed during the audit pass. It is dirty in two directions: several tracked files modified, **and** 19 tracked deletions under `.ai/audit/**`. Never `git add -A`, `git add .`, `git commit -a`, `git reset`, `git checkout`, `git stash` or `git clean`. **Stage explicit paths only** (`git add <specific-files>`) and re-read `git status --short` **immediately before every commit** rather than trusting a list captured earlier. |
| **Audit tree** | `.ai/audit/**` is **unmodifiable**. No block may edit, restore, or re-create any file under it — including the 19 currently-deleted ones. `git status --short .ai` must show no *new* modifications beyond the pre-existing deletions. |
| **Commits** | One block = one commit, staged by explicit path, message `"{type}({scope}): {description}"` matching the repository's style (`fix(...)`, `test(...)`, `docs(...)`, `chore(...)`, `refactor(...)`). Never rewrite history. **Do not commit without an explicit user request.** |
| **Implementor concurrency** | **Exactly one Implementor at a time, strictly sequential.** Other agents (Auditor / Researcher / Planner / Validator) run as analysis or review passes inside the block. Changes you did not make are normal; do not revert them. |
| **Production code is king** | If a shipped **green** test conflicts with the architecture or business logic, **fix the test, not the code** — and record the justification in the commit message. Blocks 3, 6, 8 and 9 each rewrite at least one green test; each names the test and the reason. |
| **Full suite** | `.\Makefile.ps1 test-all` (~35 min, includes `seed`) is **not** required by any block in this plan. |
| **PowerShell** | `head` and `tail` do not work. Use `Select-Object -First/-Last`, `Get-Content -TotalCount`, `Select-String`. |

---

## 2. Scope decisions table (acceptance contract for execution)

| ID | Disposition | Block | Final severity | One-line reason |
|---|---|---|---|---|
| `03-DB-001` | **implement** — add the missing savepoint; keep delete-then-recreate | BLOCK 4 | MEDIUM | The recovery branch is genuinely dead code; one nested `atomic()` fixes it and the in-repo precedent exists. Gated on `03-VAL-003` only because it is the same defect as phase 05's `AD-005`. |
| `03-DB-002` | **implement** — one function, but the fix encoding is **gated** (Q3/Q4) and the option-1 variant carries an undeclared query-budget constraint (§0.2.3) | BLOCK 3 | HIGH | A best-effort observer can abort the business transaction it was only watching. A bare savepoint does **not** fix it. |
| `03-DB-003` | **implement, whole finding in one block** — heartbeat + `updated_at` predicate + `ads/0008_*` migration + seller-facing message + `_STAGING_TTL_SECONDS` + 3 docs | BLOCK 6 | HIGH | The spec says *idle*, the code says *age since creation*; the spec-conformant fix is also the cheaper one. Not split — see BLOCK 6's grouping note. |
| `03-DB-004` | **implement, timeout half only** — the `ENT-006` addendum is **already shipped** in phase 01 `7aac8d3` | BLOCK 5 | HIGH | One blocked row lock currently stalls every DB operation in the bot and nothing bounds the wait. Ship only what phase 01 did not. |
| `03-DB-005` | **implement** — design **gated** (Q7/Q8); the design owns the media storage contract | BLOCK 8 | MEDIUM | A committed `AdImage` row can point at a file the sweep unlinked; the exposure window is the whole `os.walk`, not a millisecond race. |
| `03-DB-006` | **rejected — no work item** | — | — | The stated mechanism is a Django-internals fact that does not hold for a non-fast-deletable model. Residue is covered by `DB-011`. |
| `03-DB-007` | **implement** — delivery contract **gated** (Q9/Q10); scheduled with the `IMMEDIATE_ALERTS_ENABLED` rollout, not before | BLOCK 9 | MEDIUM | Latent (the gate is OFF), but adding the lock alone is **provably insufficient** — `find_matching_saved_searches` has no `NOT EXISTS` filter and `record_notifications` returns `len(ads)`, not the created count. |
| `03-DB-008` | **implement** — design **gated** (Q11), which is structurally unresolvable as written | BLOCK 7 | MEDIUM | Locks accumulate for the whole sweep; per DB-004 that lands on the bot's single shared worker thread. |
| `03-DB-009` | **implement** — product rule **gated** (Q12), applied in **both** draft creators | BLOCK 10 | LOW | The real defect is a raw driver error reaching a user-facing message plus an absent shared single-draft policy — not a 500. |
| `03-DB-010` | **implement** — `try/finally` in the transaction branch; **lock behaviour must not change** | BLOCK 2 | LOW | The "released" line is a proxy for "the sweep succeeded", not "the lock is free". |
| `03-DB-011` | **implement** — pure removal in six commands; no behaviour change, no test change | BLOCK 1 | LOW | One redundant `AdImage` scan per sweep, executed while the lock and transaction are held, whose only consumer is a log number. |
| `03-VAL-001` | **cross-cutting** — tracker prefix **decided** (this plan + §5.2); source-comment sweep **gated** | BLOCK 11 (+ plan-wide) | HIGH (tracker integrity) | 68 shipped citations are ambiguous and this cycle's own IDs are already cited in two production files. |
| `03-VAL-002` | **binding constraint** — `03-DB-002` must land before `03-DB-004` | BLOCK 3 → BLOCK 5 | MEDIUM | `statement_timeout` produces exactly the class of server-side error `record_event` swallows. |
| `03-VAL-003` | **binding constraint + coordinator escalation** — one work item at MEDIUM; phase 05's `AD-005` must be re-rated | BLOCK 4 (gate) | CRITICAL (process) | The final report would otherwise state a CRITICAL/HIGH pair for a defect that destroys no data. |
| `03-VAL-004` | **documentation-only** — routed to the coordinator for the final report; no code | — | MEDIUM | Two retained reproductions do not hold against the production code path. |

---

## 3. Execution blocks

Roster legend and the standing rule: **Implementor is always required, exactly one at a
time, sequentially.** Auditor / Researcher / Planner / Validator are added per block with
an explicit justification *and* an explicit statement of who is **not** required and why.
The rule "high risk ⇒ all agents" is applied to **BLOCK 3, BLOCK 5, BLOCK 6, BLOCK 7,
BLOCK 8, BLOCK 9 and BLOCK 11** — see each block for the specific reason.

Every block below carries a **decision gate** section where the code context flagged real
technical uncertainty. **A gated block must not begin implementation until the gate is
closed and the decision is written into the block's commit message.**

---

### BLOCK 1 — Drop the redundant media-key pre-collection from six sweeps (DB-011)

| | |
|---|---|
| **Findings owned** | `03-DB-011` |
| **`depends_on`** | *(none)* — executes first |
| **Priority** | P0 |
| **Roster** | **Implementor, Validator** |

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — no.** All six call sites are named in §2.11 of the code context and were
  re-verified by grep at the anchor: `delete_sweep`, `sweep_drafts`, `purge_failed_ads`,
  `purge_rejected_ads`, `purge_deleted_ads`, `consent_hard_delete`. Each builds
  `storage_keys` and consumes it only through `len(storage_keys)`. There is no
  investigative question left.
- **Researcher — no.** No external best-practice question. This is a pure removal of dead
  work.
- **Planner — no.** Six identical mechanical deletions, each three lines plus a log-line
  edit. No design to pre-author.
- **Validator — yes.** The claim being made is "no behaviour change" across six
  commands — and the *absence* of a regression is only established by an independent run
  of the six suites plus the two media-deletion suites whose invariants depend on the
  deletion still happening exactly once.

**Grouping decision.** `03-DB-011` is promoted from the report's rollout position 10 to
**first**. Rationale: it is pure removal with no behaviour change and no test change, it
**shortens** the transaction that every other sweep holds while its advisory lock is
held (so it is cheap risk reduction for BLOCK 7), and it is the lowest-altitude change in
the phase. Doing it first also means BLOCK 6's rewrite of `sweep_drafts.Command.handle`
starts from a shorter function.

**Findings and notes carried forward.**
1. **Six commands, one identical shape.** In each, the `storage_keys` list comprehension
   plus the comment `# Collect storage keys for physical media cleanup before ORM
   cascade` sits **inside** the `transaction.atomic()` + `advisory_lock(...)` block,
   immediately before the cascade delete. Its only consumer is `len(storage_keys)` in the
   closing `logger.info(...)`. The **correct** explanatory comment (*"Physical media
   deletion is handled by the `AdImage` `pre_delete` signal via `transaction.on_commit()`"*)
   already sits below the `atomic()` block in each command — leave it.
2. **The `AdImage` import may become unused in every one of the six commands** (`ruff`
   `F401`). Check each file after the removal and drop the import only where it is truly
   unused. In `consent_hard_delete` the scan is `AdImage.objects.filter(ad__user_id__in=user_ids)`,
   which is the largest of the six and uses a **different** field path than the other five —
   do not assume the imports are interchangeable.
3. **`consent_hard_delete` also logs `len(user_ids)` in the same line.** That is **not**
   redundant — it counts users, not media keys. Keep it.
4. **The `AdImage` `pre_delete` signal is the real deletion mechanism**
   (`apps/media/signals.py::delete_adimage_files_on_delete`, which collects
   `instance.storage_keys()` and defers `delete_photo` via `transaction.on_commit()`).
   Removing the pre-collection must not create a *second* deletion path.
5. **Two shipped suites depend on the mechanism this block leaves in place** and must stay
   green: `apps/core/tests/test_delete_photo_single_call.py` (asserts `delete_photo` runs
   **exactly once** per key — a duplicate deletion would appear if the sweeps had been
   doing real work) and `apps/core/tests/test_ad_image_delete_signal.py` (the whole class;
   it pins `pre_delete` deferring to `on_commit` and FS failure not rolling back the
   cascade).
6. **`sweep_drafts.py` is also BLOCK 6's surface.** BLOCK 1 must land first and BLOCK 6
   must re-read the file rather than assume this block's state.

**Implementor task (`.ai\tasks\templates\task_template.yaml` shape).**

```yaml
id: task_03_b01_remove_storage_keys_precollection
title: Remove the redundant AdImage storage-key pre-collection from six sweep commands
priority: high
depends_on: []
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 1 — Drop the redundant media-key pre-collection from six sweeps (DB-011)"

description: >
  In each of six management commands, delete the `storage_keys` list comprehension
  that pre-collects every AdImage storage key for every doomed ad inside the
  transaction.atomic() + advisory_lock block, and drop `len(storage_keys)` from the
  closing log line. Physical media deletion is already handled by the AdImage
  pre_delete signal via transaction.on_commit() and must remain the only path.

goals:
  - remove six redundant full AdImage scans executed while the sweep lock and transaction are held
  - preserve the physical-deletion contract (AdImage pre_delete -> transaction.on_commit -> delete_photo)
  - preserve every other log field, including len(user_ids) in consent_hard_delete
  - no behaviour change and no test change

files:
  - path: src/backend/apps/core/management/commands/delete_sweep.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors:
      delete: { type: assignment, value: "storage_keys = [" }
  - path: src/backend/apps/core/management/commands/sweep_drafts.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors:
      delete: { type: assignment, value: "storage_keys = [" }
  - path: src/backend/apps/core/management/commands/purge_failed_ads.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors:
      delete: { type: assignment, value: "storage_keys = [" }
  - path: src/backend/apps/core/management/commands/purge_rejected_ads.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors:
      delete: { type: assignment, value: "storage_keys = [" }
  - path: src/backend/apps/core/management/commands/purge_deleted_ads.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors:
      delete: { type: assignment, value: "storage_keys = [" }
  - path: src/backend/apps/core/management/commands/consent_hard_delete.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors:
      delete: { type: assignment, value: "storage_keys = [" }
  # plus: drop the now-unused `AdImage` import in each file where it becomes unused

changes:
  - action: delete_code
    description: Remove the storage_keys comprehension and its collection-site comment from each Command.handle.
  - action: edit_log_statement
    description: Remove the "%d media files" placeholder and its len(storage_keys) argument from each closing logger.info.
    code_hint: |
      logger.info("Deleted %d draft ads ...", deleted_count)
  - action: delete_import
    description: Remove `from apps.ads.models import Ad, AdImage` -> `from apps.ads.models import Ad` only where AdImage is no longer referenced.

acceptance_criteria:
  - no storage_keys reference remains in any of the six commands
  - the AdImage pre_delete -> transaction.on_commit -> delete_photo path is unchanged and delete_photo is still called exactly once per key
  - consent_hard_delete still logs its user count
  - uv run ruff check src/ exits 0 (no new F401) and uv run basedpyright src/ reports 0 errors
  - the six sweep suites plus test_delete_photo_single_call.py and test_ad_image_delete_signal.py are green
  - no test file is modified
```

**Tests required.**
- *Must keep passing unchanged:* `src/backend/apps/core/tests/test_sweep_delete.py`,
  `test_sweep_drafts.py`, `test_ad_image_delete_signal.py`,
  `test_delete_photo_single_call.py`, `test_sweep_lock_structure.py`, and the
  `purge_*` / `consent_hard_delete` suites.
- *Must be added/changed:* **none.** This is the one block in the phase that needs no new
  test — the finding is a pure simplification and the report states "no test change".
  Do **not** add one; adding a test that asserts the absence of a variable is testing
  trivia, not logic.
- *Gate:* `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/ src/backend/apps/ads/tests/" test`
  then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk:* deleting the `AdImage` import where it is still used elsewhere in the file
  (e.g. in a type annotation or a count). `ruff` catches this; read before deleting.
- *Risk:* an implementer "improves" the log line by replacing `len(storage_keys)` with a
  live count query — that reintroduces the very query this block deletes.
- *Risk:* touching `sweep_drafts.py`'s **predicate** here. That is BLOCK 6's work
  (`03-DB-003`). BLOCK 1 changes only the key collection.
- *Rollback:* six independent, trivially revertible deletions. No schema, no contract,
  no persisted state.

---

### BLOCK 2 — Advisory-lock release log on the rollback path (DB-010)

| | |
|---|---|
| **Findings owned** | `03-DB-010` (+ the cycle-scope re-citation of phase 03's own IDs in the same file — §3.2.1) |
| **`depends_on`** | *(none)* |
| **Priority** | P1 — cheap, and it opens a file BLOCK 11 will sweep later |
| **Roster** | **Implementor, Validator** |

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — no.** The function, the branch, the defect and the in-repo model to copy
  (the session branch's own `try/finally`) are all identified and were re-verified at the
  anchor. A grep confirms the only consumer of the release log message is the test this
  block rewrites.
- **Researcher — no.** No external question. `try/finally` around a context-manager `yield`
  is not a design choice with alternatives here.
- **Planner — no.** Two edits plus a test rewrite with the shape specified below.
- **Validator — yes.** The block **rewrites two shipped green tests that currently pin the
  defective mechanism**, and it changes a primitive used by **13 commands**. An
  independent reviewer must confirm the rewrite asserts the *new* contract (release logged
  on **rollback**) and that lock behaviour is provably unchanged.

**Findings and notes carried forward.**
1. **The defect.** `advisory_lock`'s `session=False` branch executes
   `pg_advisory_xact_lock`, logs `"Acquired transaction advisory lock %s"`, then registers
   the release message with `transaction.on_commit(...)`. `on_commit` runs **only on
   commit**, so the release line is emitted exactly when nothing went wrong and omitted
   precisely when the sweep failed. The message reads "released" but proxies "succeeded".
2. **The lock's behaviour is correct and must not change.** `pg_advisory_xact_lock`
   releases on **both** commit and rollback. The runtime check that the lock is gone after
   a rollback must continue to pass. This block changes **logging only**.
3. **The model to copy is in the same function** — the session branch already wraps `yield`
   in `try/finally` and logs the release from the `finally`. Follow it, including the
   `pg_advisory_unlock` call.
4. **Do not touch the session branch.** Phase 01 `ENT-006` residual shipped there
   (commit `7aac8d3`): the `"Requesting session advisory lock %s"` line before acquisition
   and the `migrate_locked` docstring correction. `test_migrate_locked.py::TestSessionLockLogging::test_session_lock_logs_request_before_acquire`
   is now a hard regression guard for that edit and **must stay green unchanged**.
5. **The two tests that must be rewritten** —
   `src/backend/apps/core/tests/test_advisory_lock_release_log.py`:
   - `test_transaction_scoped_lock_logs_release_on_commit` patches
     `transaction.on_commit` with `side_effect=lambda fn: fn()` so the release log fires
     inline, then asserts both "Acquired" and "Released".
   - `test_transaction_scoped_lock_registers_on_commit_callback` patches `on_commit` with
     a recorder and asserts `len(registered) == 1`.
   Both are structurally incompatible with a `try/finally` design. **Per project rule 2 the
   tests are what change.** The replacements must assert:
   (a) the release line is emitted on the **normal exit** path, and
   (b) the release line is emitted on an **exception / rollback** path, where the exception
   propagates to the caller.
   A test that only asserts (a) reproduces the original blind spot and proves nothing.
6. **The module docstring of the test file is itself wrong after the rewrite.** It states
   *"The on_commit callback fires only on successful commit — matching when
   `pg_advisory_xact_lock` releases the lock."* That is exactly the defect. Rewrite it to
   state the corrected contract.
7. **`test_sweep_lock_structure.py` asserts `session is False` for all 13 lock-taking
   commands** and drives each command through a spy. This block must leave that assertion
   satisfiable — it will, because `session` is not changing. Do **not** relax it.

#### 3.2.1 The cycle-scope re-citation (in scope for this block, deliberately)

`advisory_lock.py` is the single worst file in the ID-ambiguity problem: it cites
`DB-001` and `DB-007` for **previous** defects, `DB-010` for a **previous** defect, and —
added by phase 01 — **this cycle's** `DB-010` and `DB-004` in a three-line comment. A grep
keyed on `DB-010` is now ambiguous **within one file**.

This block normalises **only this cycle's own IDs in this file**, because the file is open
anyway and the change is two words:
- `# (see DB-010)` → `# (see a previous cycle's DB-010)` or simply drop the ID and say
  *"the transaction-scoped branch's log flow"*;
- `# phase 03's DB-004 owns any timeout wording` → `# phase 03 DB-004 owns any timeout
  wording` (cycle-scoped, matching the convention in §0.1).

The **legacy** `DB-001` / `DB-007` citations in the same file are **BLOCK 11's** subject
and are explicitly **out of scope here** — they must not be rewritten by this block,
because BLOCK 11's decision may change the shape of the rewrite.

**Implementor task (`.ai\tasks\templates\task_template.yaml` shape).**

```yaml
id: task_03_b02_advisory_lock_release_log
title: Log the transaction-scoped advisory-lock release from a finally block, not from on_commit
priority: high
depends_on: []
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 2 — Advisory-lock release log on the rollback path (DB-010)"

description: >
  In advisory_lock(), the session=False branch registers its release log via
  transaction.on_commit, so the line is emitted only when the sweep succeeded and is
  omitted precisely when an operator needs it. Wrap the body in try/finally and log the
  release from the finally, mirroring the session branch. Lock behaviour must not change.

goals:
  - emit the release log on both commit and rollback
  - leave pg_advisory_xact_lock acquisition and the RuntimeError guard untouched
  - leave the session branch untouched (phase 01 ENT-006 residual shipped there)
  - normalise this cycle's own ID citations in the same file to the 03-DB-00N form

files:
  - path: src/backend/apps/core/utils/advisory_lock.py
    targets:
      - { type: function, name: advisory_lock }
      - { type: module, name: advisory_lock }
    semantic_anchors:
      replace_in_body:
        old: "transaction.on_commit(lambda: logger.info(\"Released transaction advisory lock %s\", lock_id))"
        new: |
          try:
              yield
          finally:
              logger.info("Released transaction advisory lock %s", lock_id)
      replace_in_body:
        old: "            transaction.on_commit("
        new: "            try:"
  - path: src/backend/apps/core/tests/test_advisory_lock_release_log.py
    targets:
      - { type: function, name: test_transaction_scoped_lock_logs_release_on_commit }
      - { type: function, name: test_transaction_scoped_lock_registers_on_commit_callback }
    semantic_anchors:
      replace_in_body:
        old: '"""Unit test for PII-002: transaction-scoped advisory lock release logging.'
        new: '"""Unit test for the transaction-scoped advisory-lock release log.'
  - path: src/backend/apps/core/tests/test_sweep_lock_structure.py
    targets: [{ type: function, name: test_all_sweep_commands_lock_inside_transaction }]
    semantic_anchors: {}   # assertion must keep passing unchanged; do not edit

changes:
  - action: edit_code
    description: >
      Replace the on_commit release registration in the session=False branch with a
      try/finally around the yield, logging the release from the finally. Do not call
      pg_advisory_unlock (a transaction-scoped lock releases with the transaction).
  - action: edit_comment
    description: Normalise this cycle's own ID citations in the same file to the cycle-scoped form.
  - action: rewrite_test
    description: >
      Replace the two on_commit-shaped tests with (a) a release-logged-on-normal-exit test
      and (b) a release-logged-on-rollback test that raises inside the context manager and
      asserts the exception propagates AND the release line is in the log. Rewrite the
      module docstring, which today states the defective contract as intended.

acceptance_criteria:
  - the release line is emitted when the body raises (the case that is currently silent)
  - the release line is still emitted on the normal path
  - pg_advisory_xact_lock is still issued exactly once and no pg_advisory_unlock is added to the transaction branch
  - advisory_lock still raises RuntimeError outside an atomic block (unchanged)
  - test_sweep_lock_structure.py passes unchanged, including its `session is False` assertion
  - test_migrate_locked.py::TestSessionLockLogging passes unchanged
  - uv run ruff check src/ exits 0 and uv run basedpyright src/ reports 0 errors
```

**Tests required.**
- *Must keep passing unchanged:*
  `src/backend/apps/core/tests/test_sweep_lock_structure.py` (all of it),
  `test_migrate_locked.py`, `test_advisory_lock_ids.py`, and **every one of the 13
  lock-taking command suites**.
- *Must be changed (rewritten, not deleted):* the two named tests in
  `test_advisory_lock_release_log.py`. The rewrite must be **red against the pre-fix
  code** — specifically the rollback case must fail while the current `on_commit`
  registration is in place. A test never seen red proves nothing.
- *Need no test:* the log message text itself.
- *Gate:*
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/test_advisory_lock_release_log.py src/backend/apps/core/tests/test_sweep_lock_structure.py src/backend/apps/core/tests/test_migrate_locked.py src/backend/apps/core/tests/test_advisory_lock_ids.py" test`
  then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk (highest in this block):* accidentally adding `pg_advisory_unlock` to the
  transaction branch by copying the session branch too literally. That would be a
  **behaviour** change, not a logging one, and would emit an extra round-trip for 13
  commands. Constrain the copy to the `try/finally` and the `logger.info` line.
- *Risk:* the rewrite keeps only the normal-exit assertion and drops the rollback case —
  reproducing the finding's blind spot. The rollback test is mandatory.
- *Risk:* an implementer takes the opportunity to also "fix" the legacy `DB-001`/`DB-007`
  comments. That is BLOCK 11 and may take a different shape.
- *Rollback:* one function + one test file. Fully reversible; no schema, no contract, no
  lock-behaviour change.

---

### BLOCK 3 — `record_event` must not abort the caller's transaction (DB-002)

| | |
|---|---|
| **Findings owned** | `03-DB-002` |
| **`depends_on`** | *(none)* — but **gates BLOCK 5** (`03-VAL-002`) |
| **Priority** | P0 |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- **Implementor — yes.** Always.
- **Auditor — yes.** Two things must be re-derived before code is written, not inherited:
  (1) the **exact** call graph at the anchor, because phase 01's `ENT-005` extraction
  rewrote `login.py` and moved the precedent `record_event` relies on; (2) whether **any**
  additional `record_event` caller appeared during phases 01/02. The report's "12 call
  sites" is an overcount (9 call expressions across 6 modules, §0.2 C-4) and the number
  matters because it sizes the blast radius of Option 2.
- **Researcher — yes.** **Q3** is a genuine PostgreSQL question: `SET CONSTRAINTS ALL
  IMMEDIATE` versus a targeted `SET CONSTRAINTS <name> IMMEDIATE`, and the correct
  behaviour of each under a caller transaction that has pending deferred constraints.
  The Researcher must also confirm the libpq/PgBouncer-safety of whichever mechanism
  BLOCK 5 lands, so the two fixes compose.
- **Planner — yes.** **Q4** is explicitly *"a Planner-level product/architecture decision
  that should be made explicitly, not by an implementor"*, and it has real consequences
  against shipped tests. Choosing requires design.
- **Validator — yes.** The single load-bearing runtime premise (`SET CONSTRAINTS` inside a
  savepoint actually rescues the caller's write) is **not re-derived** (§0.2.4). An
  independent reviewer must confirm it against the Docker test database before the fix is
  believed, and must confirm the new test provokes a **real server-side** error rather
  than a mocked Python-level exception.

#### 3.3.1 Decision gate — Q3 + Q4 (must be closed before implementation)

**The problem, confirmed in the tree.** `record_event` is documented *"never raising"* and
catches bare `Exception`, returning `None`. Its module docstring claims it *"performs NO
`transaction.atomic()` so it remains transparent to the caller's transaction boundary"* —
but it **does** execute inside callers' transactions. `_fail_moderation` and
`_pass_moderation` each wrap it in their own `atomic()`, themselves nested inside
`submit_ad`'s outer `atomic()`, so Django creates a **savepoint** around the INSERT. When
that INSERT fails at the database level, PostgreSQL has already aborted the transaction,
the exception is swallowed, and the caller keeps issuing statements against a dead
transaction — or, for a deferred constraint, sees success all the way to COMMIT and loses
the entire business write.

**What genuinely remains (reachability, at the anchor).** No production path produces a
value that overflows `AnalyticsEvent.event_type` (`max_length=30`; longest enum value
`registration_created`, 20 chars) or `AdSource` (`max_length=20`), and every call site
passes a real `user.id`/`ad.id` or `None`. The reachable trigger is a concurrently
hard-deleted user (`consent_hard_delete`, advisory lock 3, hourly) racing a publish — and,
**after BLOCK 5 lands**, a `statement_timeout` `OperationalError` on exactly this INSERT.
That is why `03-VAL-002` makes this block a hard prerequisite of BLOCK 5.

**Q4 — the two encodings.**

| Option | Change | Tests it inverts | Maintainability / future evolution | Conventions |
|---|---|---|---|---|
| **A (report's preferred)** | Wrap the INSERT in a nested `transaction.atomic()` **and** issue `SET CONSTRAINTS ALL IMMEDIATE` inside that savepoint before it. The `SET` forces the deferred check to run at the savepoint instead of at COMMIT; the savepoint rollback removes the offending row and leaves the caller's transaction usable. `SET CONSTRAINTS` is itself transactional, so the mode reverts on savepoint release. | **None.** `test_record_event_inside_commit_persisted` and `test_record_event_inside_rollback_not_persisted` keep their meaning. | One function; **no** call-site edits; the "never raising" and "transaction-transparent" docstring promises become literally true, which is the cleanest resolution of a `SPEC-DEVIATION` finding. Carries the `SET CONSTRAINTS` subtlety, which is non-obvious and **must** be documented in the function docstring or it will be "simplified" away by a future reader. Also interacts with the ad-detail query budget (§0.2.3). | Matches the in-repo precedent in `auto_moderation._pass_moderation`, which already wraps a best-effort `TrustCalculator().calculate_and_save(...)` in a nested `atomic()` with a broad `except Exception` + `logger.warning`. |
| **B** | Move the write out of the caller's transaction entirely: `transaction.on_commit(lambda: record_event(...))`, or call `record_event` after the `atomic()` block exits. This is the honest expression of "analytics is an observer, not a participant". | **Two.** `test_record_event_inside_commit_persisted` and `test_record_event_inside_rollback_not_persisted` **invert meaning** under an `on_commit` design — an event recorded inside a block that later rolls back would no longer be absent, and one recorded inside a committing block would no longer be synchronously visible. Both must be rewritten with a recorded rationale. | Materially simpler to reason about; no `SET CONSTRAINTS` subtlety at all. Costs **three or more call-site edits**, changes *when* the analytics row becomes visible to concurrent readers, and changes when `ad_edit`'s reactivation branch observes it. Also **does not** fully close the hole: `on_commit` inside a *nested* atomic still runs when the *savepoint* is released, not the outer transaction — so the call-site edits must place it after the outermost block, which is a subtle per-call-site discipline. | Fewer moving parts, but violates the existing "single entry point, called from anywhere" convenience that five autocommit call sites rely on. |
| **Rejected** | A **plain** nested `atomic()` savepoint with no `SET CONSTRAINTS`. | None. | **Does not work.** The report's `V-05` reproduced it: the COMMIT still fails and the caller's business write is still lost. Shipping it closes the ticket without fixing the defect. | — |

**Q3 — `ALL IMMEDIATE` versus a named constraint.**

| Option | Change | Consequence |
|---|---|---|
| **A** | `SET CONSTRAINTS ALL IMMEDIATE` inside the savepoint. | Also re-validates the **caller's** other pending deferred constraints at the analytics-INSERT point. If the caller created a new `Ad`/`AdImage` earlier in the same transaction, those FKs are validated here too. That is probably correct (they should be valid) but it is a behaviour change the caller did not ask for. Simple, no schema introspection, robust to Django's generated-name hash changing. |
| **B** | `SET CONSTRAINTS <name> IMMEDIATE` for the two `analytics_events` FKs. | Precisely scoped — it does not touch the caller's constraints. **Requires the two generated constraint names, which embed a content hash** (`analytics_events_user_id_<hash>_fk_users_id` and `analytics_events_ad_id_<hash>_fk_ads_id`). The hash is stable for a given migration state but must be **read from the live schema**, not hard-coded from the report. If a future migration changes the columns the name changes and the statement fails loudly at runtime. |

**The Researcher must state which option it chose and why; the Implementor must read the
live constraint names from the Docker test database if Option B is chosen, and must not
copy them from the report.** If the Researcher finds Option A introduces a caller-visible
behaviour change that matters, BLOCK 3 is **escalated** rather than forced to a choice.

#### 3.3.2 Binding constraints on BLOCK 3

1. **The ad-detail query budget (§0.2.3).** `test_ad_detail_queries._QUERY_BOUND = 16`
   enumerates *"1 INSERT (AnalyticsEvent)"* as a budgeted line, and `record_event`'s own
   docstring cites the constant. Option A adds transaction-control statements to a path
   that currently runs in autocommit. The Implementor must **measure** the new count in
   the same change and either (i) raise `_QUERY_BOUND` with a stated derivation, or
   (ii) record in the commit message why the count did not change (Django's
   `CaptureQueriesContext` may not count transaction-control statements). **Do not
   silently leave the budget untouched and unexamined.**
2. **The fix must land before BLOCK 5.** `03-VAL-002`. `depends_on: BLOCK 3` on BLOCK 5
   is the enforcement.
3. **The load-bearing runtime premise must be reproduced first.** BLOCK 3's first action
   is to write and run a throwaway probe **inside the Docker test database** that: opens
   an outer `atomic()`, inserts an `AnalyticsEvent` for a user, hard-deletes that user
   from a *second* connection, attempts the INSERT, and asserts the outer COMMIT succeeds
   under the chosen encoding. If it does not, **stop and escalate** — the block's design
   rests on it. Delete the probe afterwards; do not commit it.
4. **`submit_ad`'s transaction must not move.** `apps/ads/tests/test_submission.py::test_submit_ad_rolls_back_when_auto_moderate_raises`
   pins that `auto_moderate` raising rolls back the whole `submit_ad` transaction and
   leaves the ad `DRAFT`. Option A must not weaken that.
5. **A bare mocked exception is not a regression test.** The existing
   `test_record_event_failure_returns_none_and_logs` monkeypatches
   `AnalyticsEvent.objects.create` to raise `RuntimeError`, which leaves the transaction
   perfectly usable — it **structurally cannot reach** the failure mode. The new test must
   provoke a **real server-side** error (e.g. a FK violation against a concurrently
   hard-deleted row, or a statement that genuinely aborts the transaction) and assert the
   **caller's** transaction still commits. Keep the existing test as a supplement.
6. **The module docstring is part of the defect.** It currently asserts two guarantees the
   implementation cannot honour. Whichever option is chosen, the docstring and the
   `record_event` docstring must be rewritten to state what the code actually does.

**File surface (semantic units).**
- `src/backend/apps/core/services/analytics.py` → `record_event()`; module docstring;
  `record_event`'s docstring (the "never raising" / "transparent" contract).
- **Option B only:** `src/backend/apps/moderation/services/auto_moderation.py` →
  `_fail_moderation()`, `_pass_moderation()`; `src/telegram_bot/handlers/login.py` →
  `handle_login_orm()`. **Re-read these at the anchor** — phase 01's `ENT-005` extraction
  rewrote `login.py`.
- `src/backend/apps/core/tests/test_analytics_service.py` →
  `TestRecordEvent` (supplement the mocked-failure test; under Option B, rewrite the two
  inside-transaction tests).
- `src/backend/apps/ads/tests/test_ad_detail_queries.py` → `_QUERY_BOUND` **only if the
  measured count grows** (see binding constraint 1).
- **Not touched:** `AnalyticsEvent` model or its migration (the project deliberately
  allows duplicate analytics rows and forbids `ignore_conflicts` on this table);
  `record_trust_event`; the five autocommit call sites under Option A.

**Tests required.**
- *Must keep passing unchanged:*
  `src/backend/apps/ads/tests/test_submission.py` (both named cases),
  `src/backend/apps/moderation/tests/test_auto_moderation.py`,
  `src/backend/apps/ads/tests/test_ad_detail_queries.py` (unless the bound is raised with a
  derivation),
  `src/telegram_bot/tests/test_login.py`.
- *Must be added:* a **real-server-side-error** regression test: inside a caller-owned
  `atomic()`, provoke a genuine database error in `record_event`, then assert the caller's
  business write **still commits**. Under Option A this is the `SET CONSTRAINTS` scenario;
  under Option B it is the "called after the block" scenario. It must be **red against the
  pre-fix code**.
- *Must be changed (Option B only):* `test_record_event_inside_commit_persisted` and
  `test_record_event_inside_rollback_not_persisted`, each with a docstring stating **why**
  the new contract is the correct one.
- *Gate:*
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/test_analytics_service.py src/backend/apps/ads/tests/test_submission.py src/backend/apps/ads/tests/test_ad_detail_queries.py src/backend/apps/moderation/tests/" test`
  then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk (highest):* shipping the **plain savepoint** variant. It looks like Option A,
  passes the existing suite, and does not fix the defect. The regression test above is
  the only control — and it must be demonstrated red first.
- *Risk:* the `SET CONSTRAINTS` subtlety being "simplified" away by a later reader because
  it is not documented. The docstring must state why the `SET` is mandatory.
- *Risk:* Option B's `on_commit` being placed inside a nested atomic, where it fires at
  **savepoint** release rather than at the outer commit. That would silently produce the
  bug the block is fixing. Each edited call site must be checked against the enclosing
  `atomic()` nesting.
- *Risk:* the fix is landed **after** BLOCK 5, turning a latent defect live
  (`03-VAL-002`). Enforced by `depends_on`.
- *Rollback:* one function, or one function plus three call sites. Fully reversible. The
  runtime probe is a throwaway and must not be committed.

---

### BLOCK 4 — Recoverable race backstop in `create_draft_ad` (DB-001)

| | |
|---|---|
| **Findings owned** | `03-DB-001` (`03-VAL-003` as a gate) |
| **`depends_on`** | *(none)* — **gated** on the coordinator's `03-VAL-003` acknowledgement |
| **Priority** | P1 |
| **Roster** | **Implementor, Auditor, Validator** |

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — yes.** The fix copies an in-repo precedent — an inner `transaction.atomic()`
  whose `except IntegrityError` branch runs a plain query — and the report cites it as
  `login.handle_login_orm:226-240`. **That line reference is stale** (§0.2 C-5): phase
  01's `ENT-005` extraction rewrote `login.py`. The Auditor must re-locate the precedent
  **by symbol** and confirm the caller topology is still "one production caller, one bot
  process" before the block relies on it. A second bot process appearing in any
  deployment would change the reachability argument materially.
- **Researcher — no.** The remedy is prescribed and has an in-repo model. No external
  best-practice question.
- **Planner — no.** One nested `atomic()` around one statement, plus a regression test.
  The design choice (`03-VAL-003`'s severity) is a **coordinator** decision, not a Planner
  one, and it does not change the code.
- **Validator — yes.** This is a **hot bot path** (`/post`), and the fix changes a
  transaction boundary. A regression here means `/post` breaks for every seller.

**Decision gate — `03-VAL-003` (coordinator, not an investigation).**
`AD-005` (phase 05) and `03-DB-001` (this cycle) are **the same defect**, filed **twice**
with disagreeing severities (HIGH vs MEDIUM). This plan ships **one** work item at
**MEDIUM** and escalates the phase-05 re-rating (§5.4). BLOCK 4 may proceed once the
coordinator has acknowledged the duplicate; it does **not** wait for phase 05 to act, and
phase 05 must **not** ship a second patch (§5.2).

**Findings and notes carried forward.**
1. **The mechanism, confirmed in the tree.** `create_draft_ad`'s inner `_create()` wraps
   `Ad.objects.create(...)` in the **outermost** `transaction.atomic()`. Django creates no
   savepoint for the outermost block, so the `except IntegrityError` handler's first
   statement runs against an already-aborted transaction. The branch is **dead code**.
2. **What the report gets wrong, and why it matters here.** The exception is
   `InternalError`, **not** `TransactionManagementError` — `TransactionManagementError` is
   raised only when `connection.needs_rollback` is set, and that flag is set when an
   exception passes *through* the block, which here it does not. This is unverified at
   runtime (§0.2.4) but the Django mechanism is unambiguous. The report's "the seller's ad
   is destroyed" claim is **false**: the rollback **preserves** the pre-existing DRAFT
   row, and no `pre_delete`/`on_commit` file deletion fires. A sequential retry succeeds.
   **Do not write a fix or a test that assumes data loss** — the correct invariant to test
   is *"a draft is returned"*, not *"the seller's draft survived"*.
3. **Reachability.** `create_draft_ad` has exactly **one** production caller —
   `src/telegram_bot/handlers/ad_create/entry.py::cmd_post` (the `/post` handler). The web
   process never calls it (zero references from `src/backend`; the only non-test importers
   are `entry.py` and the `telegram_bot.services.ad_data` package re-export). Within one
   bot process, concurrent calls serialise on the single asgiref `thread_sensitive`
   worker, so the unique index cannot fire. A trigger requires a second bot process.
4. **The fix must preserve delete-then-recreate.** The existing
   `existing.delete()` before the create is the documented *Option D* pattern and is the
   **sibling policy** BLOCK 10 unifies with `copy_ad`. Do **not** remove it.
5. **The minimal shape** is a nested `transaction.atomic()` around the
   `Ad.objects.create(...)` call, so the handler runs against a usable transaction. Keep
   the existing cleanup-then-retry.
6. **The docstring already describes the intended behaviour** ("fires `IntegrityError` as
   a backstop … on such a race we retry once after cleaning up"), which makes this a
   `SPEC-DEVIATION`: the code does not do what its docstring says. The fix makes the
   docstring true; no docstring rewrite is needed unless the shape changes.

**File surface (semantic units).**
- `src/telegram_bot/services/ad_data/orm.py` → `create_draft_ad()` → the inner `_create()`
  function; the `try`/`except IntegrityError` block; the `create_draft_ad` docstring.
- `src/backend/apps/ads/models.py` → the `uq_ads_single_draft_per_user`
  `UniqueConstraint` — **reference only**, not modified.
- `src/telegram_bot/tests/test_create_draft_ad.py` → `TestCreateDraftAdCrashRecovery`
  (must keep passing); a new regression test.
- **Not touched:** `src/telegram_bot/services/ad_data/__init__.py` (no new export);
  `entry.py` (no call-site change).

**Tests required.**
- *Must keep passing unchanged:*
  `test_create_draft_ad.py::test_create_draft_second_call_does_not_duplicate` and
  `TestCreateDraftAdCrashRecovery::*` (rollback preserves the DRAFT row; `delete_photo` is
  not called on rollback); `src/backend/apps/ads/tests/test_ad_constraints.py`
  (the unique constraint exists).
- *Must be added:* a test that **forces `uq_ads_single_draft_per_user` to fire** — the
  realistic way is to make the delete-then-create race deterministic (e.g. by creating a
  second DRAFT from a separate connection between the `existing.delete()` and the
  `create()`, or by patching the constraint to raise) — and assert that **`create_draft_ad`
  still returns a draft** rather than propagating an `InternalError`. It must be **red
  against the pre-fix code**.
- *Gate:*
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/telegram_bot/tests/test_create_draft_ad.py src/backend/apps/ads/tests/test_ad_constraints.py" test`
  then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk:* the new savepoint changes what a rollback of the **outer** block restores.
  Specifically: a nested `atomic()` that rolls back releases the savepoint and keeps the
  outer transaction usable, which is the intent — but the cleanup `Ad.objects.filter(...).delete()`
  inside the handler then runs **inside the outer transaction** and could itself be rolled
  back by a later failure. That is correct behaviour (the whole thing is one unit of work),
  but it must be **understood**, not assumed.
- *Risk:* "fixing" it by removing the cleanup-then-retry and relying on the constraint to
  propagate. That converts a dead net into no net.
- *Risk:* a test written against the report's wrong "the seller's ad is destroyed" claim.
  Such a test would fail against the **correct** code. The invariant is "a draft is
  returned".
- *Rollback:* one function. Trivially reversible.

---

### BLOCK 5 — Bound the lock wait and give both processes a retry boundary (DB-004, timeout half)

| | |
|---|---|
| **Findings owned** | `03-DB-004` — **timeout half only** (the `ENT-006` addendum is already shipped) |
| **`depends_on`** | **BLOCK 3** (`03-VAL-002` — a `statement_timeout` produces exactly the error `record_event` swallows) |
| **Priority** | P0 — the phase's structural block |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- **Implementor — yes.** Always.
- **Auditor — yes.** The complete inventory of `select_for_update()` call sites that would
  **newly gain an `OperationalError` path** must be re-derived at the anchor and split
  bot-side from web-side (§0.2 C-1). Missing one means a new unhandled `OperationalError`
  surfaces as a 500 or an unhandled bot exception. Phase 01/02 have edited `login.py`,
  `scheduler.py` and `base.py` since the report was written.
- **Researcher — yes.** **Q1** is a genuine, multi-viable-approach question with
  deployment implications (libpq parameter vs. `SET LOCAL` vs. PgBouncer interaction), and
  **Q2** needs a survey of error-boundary patterns that neither process currently has.
- **Planner — yes.** The block touches a **shared settings module** that another phase is
  editing concurrently, introduces a **new env var** if Option A is chosen (which then
  needs an `ALLOWED_ENV_VARS` entry and four template updates in the same change), and
  designs a shared error boundary that must work in **two different execution models**
  (gunicorn sync views and aiogram async handlers).
- **Validator — yes.** HIGH; a timeout converts hangs into errors **everywhere**, so every
  row-locking call site gains a new failure mode that must be handled or it surfaces as a
  500. No existing test asserts a bounded wait; the claim is only established by a new one.

#### 3.5.1 Decision gate — Q1 (timeout mechanism)

| Option | Change | Blast radius | Test impact | Deployment impact |
|---|---|---|---|---|
| **A** | A global `lock_timeout` (and optionally `statement_timeout`) in `DATABASES["default"]["OPTIONS"]`, as a libpq connection parameter in **milliseconds** (`0` disables). | Every statement in both processes. Also **breaks six shipped concurrency tests** that deliberately hold a row lock for ~1 s and assert the waiter is still blocked: `currencies/tests/test_recompute_command.py::TestRecomputeRowLockConcurrency`, `core/tests/test_sweep_archive.py::TestArchiveSweepRowLockConcurrency`, `apps/ads/tests/test_transition_concurrency.py`, `apps/moderation/tests/test_admin_actions.py` (bulk_reject), `telegram_bot/tests/test_unsubscribe.py`, and the `test_ad_detail_queries`-adjacent locking guards. All use `django_db(transaction=True)`. | Requires **both** a value chosen comfortably above the tests' ~1 s holds (or a deliberate update of those six tests) and an `ALLOWED_ENV_VARS` entry plus **four** `.env.*.example` updates in the same change. Also must be added to **both** `base.py` branches, because the first branch **replaces** `OPTIONS` wholesale — and the second branch is dead in deployment but still parsed. | A **session-level** `SET` is unsafe under PgBouncer transaction-mode pooling; a libpq **connection** parameter set at connect time is safe. Needs an explicit statement of which the deployment uses. |
| **B (context's lean)** | `SET LOCAL lock_timeout` scoped to the ~12 `atomic()` blocks that actually take row locks. | Precise. Touches `apps/ads/services/submission.py`, `telegram_bot/handlers/login.py`, `telegram_bot/handlers/alerts.py`, `apps/ads/views/edit.py`, `apps/ads/views/delete.py`, `apps/moderation/views/review.py`, `apps/moderation/admin_actions.py`, `apps/moderation/services/moderation_log.py`, `apps/core/management/commands/archive_sweep.py`, `apps/currencies/management/commands/recompute_normalized_prices.py`. | **Zero** impact on the six concurrency tests (they do not go through the patched code paths… **which must be verified**, not assumed — `test_sweep_archive`'s concurrency case *does* exercise `archive_sweep`). No env var, no `ALLOWED_ENV_VARS` entry, no template churn, no collision with phase 02. | `SET LOCAL` is **safe** under PgBouncer transaction-mode pooling. It is transactional, so it reverts at commit/rollback and cannot leak to the next transaction. It must be re-established on **every** transaction, which is exactly what "scoped per `atomic()`" means. |

**Additional constraints on the answer.**
- **`test_sweep_archive.py::TestArchiveSweepRowLockConcurrency` exercises
  `archive_sweep.Command.handle` itself.** Option B's `SET LOCAL` in that command will
  therefore land inside a test that holds a lock for ~1 s. Either the value is comfortably
  above 1 s or that test must be updated **deliberately**. This is the sharpest instance of
  the risk the code context flagged; the Researcher must resolve it explicitly, not
  generically.
- **`test_sweep_lock_structure.py` asserts `session is False`** for all 13 lock-taking
  commands. Neither option changes that, but the Researcher must confirm.
- **libpq units are milliseconds.** A value written in seconds is a 1000× error and is
  exactly the kind of silent misconfiguration this block exists to prevent. Whatever value
  is chosen, the constant must be named, typed, and documented with its unit.
- **BLOCK 7 and BLOCK 9 both add `atomic()` blocks or read this setting.** The mechanism
  chosen here must be re-usable there; if it is Option B, BLOCK 7 and BLOCK 9 must be able
  to apply it without inventing a second convention.

#### 3.5.2 Decision gate — Q2 (error boundary and message ownership)

Neither process has a bounded-retry `OperationalError` boundary today: the web tier is
gunicorn sync views, the bot is aiogram handlers. The Researcher must enumerate the full
`select_for_update` inventory and propose, **per call site**, whether it gets a bounded
retry or a user-facing error. Three candidate homes:

| Option | Change | Pro | Con |
|---|---|---|---|
| **A** | A shared helper in `src/backend/apps/core/utils/` (e.g. a bounded-retry context manager for lock acquisition), called explicitly at each row-locking site. | Explicit at the call site; follows the `services/`/`utils/` convention; no hidden behaviour; each site chooses retry-vs-error itself. | The call sites are in **two processes and ~10 modules**; "explicit" means ten edits that must all be reviewed. |
| **B** | A web middleware in `apps/core/middleware/` for the web tier plus a bot middleware/handler decorator for the bot tier. | Uniform per-request behaviour; the web tier gets one place. | A middleware cannot know whether a given 500 is a lock timeout or a real bug; it would mask unrelated errors. Two mechanisms, two conventions. |
| **C** | Handle `OperationalError` **only** at the sites that already have a user-facing error path (the bot's seller-facing messages, the web views' error responses), and log-and-re-raise elsewhere. | Smallest change; no new abstraction; matches project rule 5 (avoid overengineering). | The retry behaviour is duplicated per site and can drift. |

**The Researcher must state its recommendation; this plan does not choose.** What it must
*not* do is "fix" the finding by **raising the asgiref worker count** — `thread_sensitive`
exists so a transaction and its connection stay on one thread, and relaxing it breaks the
single-dispatch-per-transaction guarantee the project documents.

**Findings and notes carried forward.**
1. **What is already shipped and must not be re-shipped.** `ENT-006`'s two residual
   elements landed in phase 01 commit `7aac8d3`: the `migrate_locked` module docstring now
   correctly says a contending run *blocks*, and `advisory_lock`'s session branch emits
   `"Requesting session advisory lock %s"` **before** acquisition. BLOCK 5 adds **no**
   timeout wording to `advisory_lock.py` and does not re-touch `migrate_locked.py`.
2. **The bot-side blast radius, corrected.** A blocked row lock stalls the bot because all
   bot DB work serialises on the **single** asgiref `thread_sensitive` worker owning one
   thread-local connection. The genuine bot-side waiters are `submit_ad`,
   `handle_login_orm`, and the `SavedSearch` toggle in `telegram_bot/handlers/alerts.py`.
   `ad_edit`, `ad_archive` and `ad_reactivate` are **web views** and are bounded only by
   `gunicorn.conf.py`'s `timeout = 60`, at which point the worker is SIGKILLed mid-request
   and the transaction goes to PostgreSQL's rollback. **The asyncio event loop is not
   blocked** — the handler awaits.
3. **Do not shorten the wait by raising the worker count.** See above.
4. **The doc correction this block owns.** `docs/02-database/db-retention.md` still says
   verbatim *"a contending run **blocks** until the lock is granted (**no lock timeout is
   configured**)"*. Once a timeout lands that sentence is false and must be corrected in
   the same change.
5. **`base.py` structure, verified at the anchor.** The `DATABASE_URL` branch (the one that
   runs, because compose injects `DATABASE_URL` into every service) does
   `DATABASES["default"]["OPTIONS"] = {"prepare_threshold": None}`, **replacing**
   `OPTIONS` wholesale. Any new `OPTIONS` key must be added to **both** branches, and a
   `?options=-c …` query parameter in `DATABASE_URL` would be silently clobbered.
6. **Do not re-open `CONN_MAX_AGE` / connection lifecycle.** `CONN_MAX_AGE = 0` is
   documented intentional design ("PgBouncer async safety (zone C5)") and phase 01's
   `ENT-010` Half B was **rejected as intentional design**. `CONN_HEALTH_CHECKS` is set
   nowhere (§0.2 C-2) — record that, do not "fix" it.
7. **Coordination is mandatory, not advisory.** Phase 02 BLOCK 5 (`CFG-005`) edits
   `base.py` and `.env.*.example`; Phase 02 BLOCK 6 (`CFG-008`/`CFG-009`) adds a
   reverse-direction consumed↔allowlist parity test that will pick up any new env var.
   Under Option A the new setting must land **with** its `ALLOWED_ENV_VARS` entry and its
   four template updates in a single commit, and the implementor must re-read `base.py`
   immediately before editing.

**File surface (semantic units).**
- `src/backend/config/settings/base.py` → the `DATABASES` block (**both** branches); a new
  named timeout setting (Option A) **and** its `ALLOWED_ENV_VARS` entry.
- **Option B only:** a new shared helper (e.g. in `src/backend/apps/core/utils/`) plus
  `SET LOCAL` at the top of each row-locking `transaction.atomic()`.
- Row-locking call sites (see the §2.1 inventory in the code context, re-derived by the
  Auditor): `apps/ads/services/submission.py::submit_ad`;
  `telegram_bot/handlers/login.py::handle_login_orm`;
  `telegram_bot/handlers/alerts.py`;
  `apps/ads/views/edit.py::ad_edit` / `ad_archive` / `ad_reactivate`;
  `apps/ads/views/delete.py`; `apps/moderation/views/review.py::approve_ad` / `reject_ad` / ban;
  `apps/moderation/admin_actions.py::bulk_approve` / `bulk_reject` / `bulk_delete` /
  `ban_user_for_ad`; `apps/moderation/services/moderation_log.py::set_published` /
  `set_moderation_failed`; `apps/core/management/commands/archive_sweep.py::Command.handle`;
  `apps/currencies/management/commands/recompute_normalized_prices.py::Command.handle`.
- `.env.example`, `.env.dev.example`, `.env.prod.example`, `.env.test.example`
  (Option A only).
- `docs/02-database/db-retention.md` → the "no lock timeout is configured" sentence.
- `src/telegram_bot/middlewares/connection.py` → **only** if a per-update reset is
  genuinely required (the Researcher must justify it; `CONN_MAX_AGE = 0` means the
  connection is closed per update already).

**Tests required.**
- *Must keep passing unchanged:* the **six shipped concurrency tests** that deliberately
  hold a lock for ~1 s — they are the reason the value must be chosen carefully. Also
  `test_sweep_lock_structure.py` (the `session is False` assertion),
  `test_sweep_archive.py::test_archive_sweep_handle_uses_select_for_update_and_atomic`,
  `apps/moderation/tests/test_admin_actions.py::test_bulk_ban_users_must_not_gain_select_for_update`
  (scope discipline), `telegram_bot/tests/test_unsubscribe.py`, and
  `config/settings/tests/test_env_allowlist.py` in full (Option A).
- *Must be added:*
  - **A bounded-wait test.** Hold a row lock from one connection and assert the
    timeout-bound call **fails fast with a bounded wait** rather than hanging. This is the
    finding's substance and no test today asserts it. It must be **red against the
    pre-fix code** (which hangs).
  - A test that the configured value is expressed in the documented unit (e.g. a settings
    assertion that a value of `3` does not mean 3 seconds silently) — cheap and it prevents
    the 1000× class of bug.
  - Option A only: an env-var parity assertion — the new variable is in
    `ALLOWED_ENV_VARS`, appears in all four templates, and is picked up by phase 02's
    reverse-direction test when it lands.
- *Gate:*
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/config/settings/tests/ src/backend/apps/core/tests/ src/backend/apps/ads/tests/ src/backend/apps/moderation/tests/ src/telegram_bot/tests/" test`
  then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk (highest):* a global timeout below ~1 s turns six shipped concurrency tests red
  and the implementer "fixes" the tests instead of the value. The value must be chosen so
  those tests keep asserting what they mean, **or** their intent must be preserved under a
  deliberate, recorded change — never silently adjusted.
- *Risk:* a new `OperationalError` path in a web view surfacing as an uncaught 500. The
  Q2 inventory exists to prevent exactly this.
- *Risk:* clobbering phase 02's concurrent edits to `base.py` or a template.
- *Risk:* a `SET LOCAL` added to an `atomic()` that is itself nested inside a longer
  transaction — the `SET` reverts at the **enclosing** transaction boundary, not at the
  savepoint. The implementor must know which case each `atomic()` is.
- *Rollback:* the setting/helper and the per-site edits are independently revertible, but
  the **error handling** at each call site must be reverted together with the setting, or
  the code carries a handler for an error that can no longer occur. No schema change.

---

### BLOCK 6 — Idle-timeout semantics for drafts (DB-003)

| | |
|---|---|
| **Findings owned** | `03-DB-003` |
| **`depends_on`** | BLOCK 1 (soft: same file, `sweep_drafts.Command.handle`) |
| **Priority** | P1 |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Grouping decision (why this is one block, not three).** `03-DB-003` has three parts that
look separable: (1) the bot heartbeat + `updated_at` predicate + index migration; (2) the
seller-facing "your draft expired" message; (3) the `_STAGING_TTL_SECONDS` re-derivation.
They are **one end-to-end contract** — "an idle draft is reaped, a live one is not" — and
splitting them produces three states in which the *system is worse than before*:
predicate-without-heartbeat changes nothing; heartbeat-without-predicate changes nothing;
message-without-predicate is a message nobody ever sees. The migration risk and the i18n
risk are isolated **inside** the block by the mandatory internal order below, which is
cheaper than three blocks with three review passes over the same function.

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- **Implementor — yes.** Always.
- **Auditor — yes.** The FSM step inventory must be re-derived at the anchor: which
  handlers actually mutate the ad's inputs, and whether phase 01/02 changed any of them.
  A missed handler means a dialog that stalls at that step for 30 minutes is still reaped
  — the exact defect. The Auditor must also confirm **no** other code path filters drafts
  by `created_at`.
- **Researcher — yes.** **Q5** (per-handler call vs. new middleware, and the per-dialog
  write cost) and **Q6** (whether the heartbeat must also protect `staging/` files, and
  how `_STAGING_TTL_SECONDS` must be re-derived) are both genuine.
- **Planner — yes.** This introduces a **new bot↔DB write contract**, a **schema
  migration**, a **new user-visible string**, and **two shipped green tests must be
  rewritten**. That is the definition of "detailed pre-implementation design".
- **Validator — yes.** HIGH; the change alters **retention semantics**, so a wrong choice
  either reaps live drafts (data loss, the original defect) or keeps junk forever
  (unbounded storage). Neither failure is visible in the suite.

#### 3.6.1 Decision gate — Q5 (heartbeat mechanism)

| Option | Change | Pro | Con |
|---|---|---|---|
| **A** | An explicit `touch_draft(ad_id)` helper in `src/telegram_bot/services/ad_data/orm.py`, called from each FSM handler that changes an ad input. | Explicit and greppable; follows the existing `ad_data` service boundary and the module's "all DB access wrapped in `sync_to_async`" contract; no new cross-cutting machinery; a missing call is visible in a handler's diff. | ~10 touch points across six handler modules; a missed handler is invisible; one extra `UPDATE` per dialog step (up to ~10 per dialog) on the single shared worker thread. |
| **B** | A new aiogram middleware in `src/telegram_bot/middlewares/` keyed on the `AdCreateForm.*` states, touching the draft once per update before the handler runs. | One touch point; cannot be missed by a future handler added to the FSM. | **New cross-cutting machinery in a package that currently has four middlewares**; must read FSM state before the handler runs and must know the draft id; it also fires for updates that changed nothing, so the write count is the same or higher; middleware ordering becomes load-bearing. |

**Researcher must additionally quantify**: whether the heartbeat is fire-and-forget (one
`UPDATE` per step) or can piggyback on an existing write (e.g. the photo save).
**The `ad_data` service boundary is a hard constraint either way** — the helper belongs in
`telegram_bot/services/ad_data/orm.py` and must be added to that package's `__init__.py`
re-export and `__all__`.

#### 3.6.2 Decision gate — Q6 (staging TTL and whether staging needs protecting)

With an `updated_at` heartbeat a dialog can span **arbitrarily** long (as long as the
seller keeps stepping). `_STAGING_TTL_SECONDS` is currently `2 * 60 * 60` with the comment
*"2 hours — safely beyond the 30-minute DRAFT retention"*. Under the new semantics a seller
could upload a photo at step 1, step through nine more screens over three hours, and have
`_reclaim_stale_staging` delete a file the FSM still references.

The Researcher must decide and state:
- whether the staging TTL should be re-derived from the **inactivity** window (making it
  a moving target the reaper cannot track, since the reaper only sees file mtime) or from
  a **worst-case dialog duration** the product accepts;
- whether the heartbeat must also **touch the staging files** (an `os.utime`) — note this
  is a filesystem write, so it must respect the TX-then-FS convention and must not run
  inside a transaction;
- or whether the honest answer is that a seller who abandons a dialog for N hours loses
  their photo, and that is acceptable and must be documented.

**Findings and notes carried forward.**
1. **The defect is a spec deviation, and the spec is already on the implementation's side.**
   `docs/01-spec/technical-specification.md` says *"Abandoned draft auto-deleted on
   **idle** timeout (e.g. 30 min)"* and `docs/04-user-stories/seller-stories.md` says
   *"Abandoned drafts auto-deleted on **idle** timeout (~30 min)"*. The code measures
   **age since row creation** from `created_at` (`auto_now_add`, stamped at `/post`) with
   no heartbeat. `Ad.updated_at` (`auto_now`) exists and is the natural activity signal;
   nothing writes it before submission.
2. **The report's rejected alternative must stay rejected.** Option (b) — "widen the
   window to a value no human conversation can exceed" — is rejected because
   `docs/02-database/db-retention.md` states *"All retention values are hardcoded… No
   environment variables or CLI arguments (beyond `--dry-run`) are read for retention
   durations."* Making the window arbitrary contradicts a documented design decision.
   **Keep 30 minutes.**
3. **The index must change with the predicate.** `Ad.Meta.indexes` declares
   `IX_ads_draft_sweep` on `fields=["status", "created_at"], condition=Q(status=DRAFT)`.
   Switching to `updated_at` requires a new migration `ads/0008_*` doing
   `RemoveIndex` + `AddIndex` on `(status, updated_at)`. `docs/02-database/db-indexes.md`
   documents the index and is a **third** DOC-UPDATE for this block.
4. **Two shipped green tests must be rewritten, not merely supplemented.**
   `src/backend/apps/core/tests/test_sweep_drafts.py`:
   - `test_deletes_drafts_older_than_30_minutes` back-dates `created_at` to −90 min and
     expects deletion;
   - `test_collects_thumbnail_keys_for_media_cleanup` does the same and expects the ad plus
     all thumbnail keys deleted.
   `create_test_ad()` in `src/backend/conftest.py` never sets `created_at` or `updated_at`
   (both `auto_*`), and `.update(created_at=…)` bypasses `auto_now`, so those ads keep
   `updated_at = now`. Under the new predicate both tests would fail. They must be
   rewritten to back-date **`updated_at`**. The other three `created_at` back-dates in that
   file assert **survival** and pass either way — do not touch them.
   **Do not change `src/backend/conftest.py`'s `create_test_ad`** (shared fixture — §5.3);
   do the back-dating locally in the tests.
5. **The failure surface, confirmed in the tree.** `submit_ad` does
   `Ad.objects.select_for_update().get(id=input.ad_id)` and returns
   `(False, ["Ad not found"])` on `Ad.DoesNotExist`. The bot's `process_preview` renders
   that as the **generic** `_("Ad failed moderation. Please check your content and try
   again.")` and then clears the state — so a reaped draft loses all typed work with a
   misleading message. This is the finding's concrete impact and it needs a
   **seller-recoverable** message (recommendation #2), which is a **new user-visible
   string** and therefore an i18n obligation.
6. **`uq_ads_single_draft_per_user` is a unique *index*, not a deferrable constraint**, so
   `SET CONSTRAINTS` cannot defer it — relevant only to BLOCK 3's reasoning, recorded here
   so no implementor confuses the two.
7. **Mandatory internal order** (a wrong order reaps live drafts):
   `(a)` add the heartbeat helper → `(b)` add the migration and flip the predicate →
   `(c)` change the failure surface → `(d)` update docs and translations →
   `(e)` run `.\Makefile.ps1 test-recreate`, then the suite.
   Landing (b) before (a) is not a data-loss event (`updated_at` equals `created_at` for an
   untouched draft) but it also delivers no benefit and leaves the sweep window wrong for
   every dialog that has taken a step.

**File surface (semantic units).**
- `src/backend/apps/core/management/commands/sweep_drafts.py` → `Command.handle` (the
  predicate), the module docstring, `Command.help`, and the `--dry-run` help string.
- `src/backend/apps/ads/models.py` → `Ad.Meta.indexes` → the `IX_ads_draft_sweep` entry.
- **New:** `src/backend/apps/ads/migrations/0008_<change_ix_ads_draft_sweep>.py`.
- `src/telegram_bot/services/ad_data/orm.py` → a new `touch_draft`-style helper (Option A);
  `src/telegram_bot/services/ad_data/__init__.py` → its re-export and `__all__` entry.
- `src/telegram_bot/handlers/ad_create/{entry,category,city,text,price,photos}.py` → the FSM
  step handlers that change an ad input (Option A), **or** a new middleware in
  `src/telegram_bot/middlewares/` (Option B).
- `src/telegram_bot/handlers/ad_create/submit.py` → `process_preview` (the error surface).
- `src/backend/apps/ads/services/submission.py` → `submit_ad` (the "Ad not found" branch).
- `src/backend/apps/media/management/commands/sweep_orphaned_media.py` →
  `_STAGING_TTL_SECONDS` and its comment. **Shared with BLOCK 8 — see §5.3.**
- Docs: `docs/02-database/db-retention.md`, `docs/02-database/db-indexes.md`,
  `docs/01-spec/technical-specification.md`, `docs/04-user-stories/seller-stories.md`,
  `docs/99-agent/architecture.md`.
- i18n: `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` — **shared artefact, §5.3.**
- **Not touched:** `src/backend/conftest.py`.

**Tests required.**
- *Must be changed (rewritten, per project rule 2):*
  `test_sweep_drafts.py::test_deletes_drafts_older_than_30_minutes` and
  `::test_collects_thumbnail_keys_for_media_cleanup` — back-date `updated_at` instead of
  `created_at`, and add a docstring line stating why (the predicate measures inactivity).
- *Must be added:*
  - A test that back-dates **`updated_at`** and asserts the draft **survives**, while
    `created_at` is old — the direct regression guard for the finding.
  - A test that a draft whose `updated_at` is old **and** whose `created_at` is very old is
    deleted (the predicate must not accidentally become "created OR updated").
  - A test that the heartbeat is written on a dialog step and that the FSM is otherwise
    unchanged (one focused test per chosen mechanism, not per handler).
  - A test that `submit_ad` returns the **draft-expired** error and that the bot renders a
    **translated**, seller-recoverable message.
  - A test that `process_preview` no longer renders the generic moderation-failure message
    for an expired draft.
- *Must keep passing unchanged:*
  `test_sweep_drafts.py::test_dry_run_does_not_delete`,
  `::test_does_not_touch_published_drafts`,
  `::test_dedup_migration_collapses_duplicate_drafts`,
  `::test_lock_id_is_sweep_drafts`; `src/backend/apps/ads/tests/test_submission.py`;
  `src/backend/apps/ads/tests/test_i18n_completeness.py` and `test_i18n_pipeline.py`;
  `src/backend/apps/media/tests/test_sweep_orphaned_media.py::test_staging_file_survives_sweep`,
  `::test_stale_staging_file_reclaimed`, `::test_fresh_staging_file_preserved`.
- *Gate:*
  `.\Makefile.ps1 test-recreate` **first** (new migration), then
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/test_sweep_drafts.py src/backend/apps/ads/tests/test_submission.py src/telegram_bot/tests/ src/backend/apps/media/tests/test_sweep_orphaned_media.py" test`,
  then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk (migration):* a wrong `updated_at` choice either reaps live drafts or keeps junk
  forever. `IX_ads_draft_sweep` **must** change with the predicate or the sweep degrades
  to a sequential scan on the hottest table.
- *Risk:* the heartbeat write lands on the single asgiref worker thread, adding ~10 UPDATEs
  per dialog to the same queue DB-004 is about to bound. The write must be a single-column
  `UPDATE`, not a full save, and must not open a transaction of its own beyond the
  statement.
- *Risk:* the new user-visible string ships without complete `ru`/`bs` translations and
  reddens the i18n gate.
- *Risk:* BLOCK 8 also edits `sweep_orphaned_media.py`. Sequential Implementor handles it;
  BLOCK 8 must re-read `_STAGING_TTL_SECONDS` rather than assume this block's value.
- *Rollback:* the migration is reversible (`RemoveIndex`+`AddIndex` back). The code halves
  are independently revertible, but **rolling back the predicate while keeping the
  heartbeat is harmless and rolling back the heartbeat while keeping the predicate restores
  the original defect** — revert both or neither.

---

### BLOCK 7 — Per-batch commit with the advisory lock held once (DB-008)

| | |
|---|---|
| **Findings owned** | `03-DB-008` |
| **`depends_on`** | **BLOCK 5** (both edit `archive_sweep.Command.handle` and `recompute_normalized_prices.Command.handle`; whichever timeout mechanism is chosen may live there) |
| **Priority** | P2 |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- **Implementor — yes.** Always.
- **Auditor — yes.** Three shipped tests encode the current structure and must be mapped
  precisely — `test_sweep_archive.py::test_archive_sweep_handle_uses_select_for_update_and_atomic`
  (does `inspect.getsource(Command.handle)` and asserts both `"transaction.atomic"` **and**
  `"select_for_update"` appear **inside `handle`**),
  `test_sweep_lock_structure.py::test_all_sweep_commands_lock_inside_transaction` (asserts
  **exactly one** `advisory_lock` call per command across all 13, with `in_atomic_block is
  True` and `session is False`), and
  `currencies/tests/test_recompute_command.py::test_process_batch_uses_select_for_update`
  (asserts `"select_for_update" in inspect.getsource(Command._process_batch)`). If batching
  moves `select_for_update` into a helper, the first and third break and must be re-pointed
  at the helper — **in the same change**.
- **Researcher — yes.** **Q11** is structurally unresolvable as written and needs a real
  survey of advisory-lock strategies under per-batch commits.
- **Planner — yes.** The block changes the **transaction contract** of two commands and
  must preserve two stated invariants while relaxing a third. That is design work.
- **Validator — yes.** The change silently weakens mutual exclusion if Q11 is resolved
  wrongly — a failure mode with **no** test that can catch it by inspection.

#### 3.7.1 Decision gate — Q11 (lock held once across per-batch commits)

**The tension, stated exactly.** `pg_advisory_xact_lock` releases with the **enclosing
transaction**. So:

- Keep the enclosing `atomic()` open around the loop ⇒ the per-batch "commits" are **not
  real commits** and the fix is theatre.
- Commit per batch ⇒ the enclosing transaction ends at the first batch boundary ⇒ the
  lock is released ⇒ a second invocation can interleave, which is **strictly worse** than
  the current behaviour.
- `advisory_lock(session=False)` **requires** an enclosing `atomic()` (it raises
  `RuntimeError` otherwise), so the transaction-scoped lock cannot simply be moved out.

| Option | Change | Mutual exclusion | Test impact | Deployment caveat |
|---|---|---|---|---|
| **A** | **Session-scoped** advisory lock (`advisory_lock(..., session=True)`) held for the whole sweep, with explicit `pg_advisory_unlock` in a `finally`, and each batch in its own `transaction.atomic()`. | Real and correct — the lock spans every batch. | **`test_sweep_lock_structure.py` asserts `session is False` for both commands.** That assertion must be amended, with the amendment justified in the test's docstring, and the assertion for the **other 11** commands must remain unchanged. | `session=True` is documented in the project as the **pre-PgBouncer** shape. On a normal connection it is a behaviour change. Under **PgBouncer transaction-mode pooling** a session lock is bound to a pooled backend connection and is **not** safe — this must be stated explicitly and checked against the deployment. |
| **B** | Keep the transaction-scoped lock but hold it on a **dedicated connection** that spans the batches, while the batch transactions run on another connection. | Real and correct, and PgBouncer-safe. | Same `session is False` assertion problem if `advisory_lock(session=True)` is used on that connection — though the assertion is about the *command's* acquisition call. | Two connections from one process during a sweep. The bot/web tiers close connections per update (`CONN_MAX_AGE = 0`), so a second connection here is new behaviour. |
| **C** | Keep the single outer transaction and **do not** batch — ship only a `lock_timeout` so a contended batch fails fast. | Unchanged (correct today). | None. | **Does not fix DB-008.** It addresses the *waiter*, not the *hold*. `backfill_thumbnails` (short transaction + lock only for the count-to-mutate sequence) is the in-repo model the report cites, so Option C leaves a known-good pattern on the table. |
| **D** | Defer the whole block until `IMMEDIATE_ALERTS_ENABLED`-style scheduling allows a larger change, and land only the lock-ordering hardening (`order_by("pk")` preservation). | Unchanged. | None. | Keeps a MEDIUM contention finding open. Recorded as the de-scope option if the coordinator prefers it. |

**The Researcher must resolve Q11 before any batching code is written** — it is the
difference between a working fix and one that silently loses mutual exclusion.

**Findings and notes carried forward.**
1. **The problem, confirmed in the tree.** `archive_sweep.Command.handle` wraps the entire
   sweep in one `transaction.atomic()` and iterates every eligible ad inside it, calling
   `transition_to()` per row (a `refresh_from_db()` + a `save()` + `post_save` →
   search-cache invalidation). `recompute_normalized_prices` is worse in shape: it walks
   the entire non-draft table in 500-row batches, taking `select_for_update()` per batch,
   **all inside the one outer transaction** — so the locks **accumulate**.
2. **The two invariants that must survive any relaxation:**
   1. The advisory lock is still taken **once** and held across every batch. Moving the
      commit inside the loop while the lock is released per batch is strictly worse than
      today.
   2. The queryset is **re-derived at the start of each batch** rather than iterated from a
      single long-lived cursor, so batch *N+1* cannot act on rows batch *N* already changed.
3. **Lock-ordering is a deadlock hazard, not a detail.**
   `archive_sweep` already uses `.order_by("pk")` **specifically** to make lock ordering
   deterministic. Any per-batch re-derivation **must** preserve it, or batch *N+1* can lock
   rows in a different order than a concurrent `ad_edit` does.
   `recompute_normalized_prices` batches by ascending `pk` via
   `.values_list("pk", flat=True).iterator()` but issues
   `select_for_update().filter(pk__in=batch_ids)` — PostgreSQL is **free to lock in any
   order**. If re-derived per batch, **an explicit ordering must be added**.
   `ARCHIVE_SWEEP` (1) and `RECOMPUTE_NORMALIZED_PRICES` (12) are distinct, so the two
   commands cannot deadlock against each other on the advisory lock — they can only contend
   on `Ad` row locks.
4. **What is genuinely lost by relaxing all-or-nothing**, and must be stated in the block's
   commit message: a mid-sweep failure leaves earlier batches applied and the sweep
   re-runs on the next tick. **Re-running is safe** for both commands — their predicates are
   time-based and re-derived, `transition_to` is idempotent per row, and
   `recompute_normalized_prices` already skips rows whose normalised value is unchanged.
   What is lost is the **meaning of the outcome**: *"Archived N ads"* becomes a per-batch
   count, and a non-zero exit no longer implies the whole population was processed.
5. **Cadence, corrected.** `archive_sweep` is hourly (`HOURLY_COMMANDS` in
   `apps/core/utils/scheduler.py`); `recompute_normalized_prices` is in **neither**
   `HOURLY_COMMANDS` nor `DAILY_COMMANDS` and is **operator-triggered only**. The report's
   evidence cited the hourly list for both; corrected in §0.2 C-6. `HOURLY_COMMANDS` and
   `DAILY_COMMANDS` themselves are **not modified** by this block.
6. **The model to copy is `backfill_thumbnails`** — short transaction + lock only for the
   count-to-mutate sequence. It is the existing, shipped, correct pattern.

**File surface (semantic units).**
- `src/backend/apps/core/management/commands/archive_sweep.py` → `Command.handle`.
- `src/backend/apps/currencies/management/commands/recompute_normalized_prices.py` →
  `Command.handle`, `Command._recompute`, `Command._process_batch`, `_BATCH_SIZE`.
- `src/backend/apps/core/tests/test_sweep_lock_structure.py` →
  `TestSweepLockOrdering::test_all_sweep_commands_lock_inside_transaction` (**only** if
  Option A/B changes `session` for these two commands; the other 11 assertions unchanged).
- `src/backend/apps/core/tests/test_sweep_archive.py` →
  `test_archive_sweep_handle_uses_select_for_update_and_atomic` (**re-pointed** at the
  helper if `select_for_update` moves out of `handle`).
- `src/backend/apps/currencies/tests/test_recompute_command.py` →
  `test_process_batch_uses_select_for_update` (re-pointed only if `_process_batch` moves).
- **Not touched:** `apps/core/utils/scheduler.py`'s command lists; `Ad.transition_to`;
  `IX_ads_archive_sweep`.

**Tests required.**
- *Must keep passing unchanged:* all of `test_sweep_archive.py` **except** the re-pointed
  structural case; all of `test_sweep_delete.py`; the 11 non-affected entries in
  `test_sweep_lock_structure.py`.
- *Must be added:*
  - **A failure-in-batch-*N* test** asserting that batches 1..*N*-1 **are committed** —
    i.e. the **opposite** of what the current code implies, and the direct assertion of the
    finding. It must be **red against the pre-fix code**.
  - A test asserting the advisory lock is acquired **exactly once** across a multi-batch
    run and held for the whole sweep (the invariant-1 guard, independent of
    `session=True|False`).
  - A test asserting the queryset is **re-derived per batch** (e.g. a row that becomes
    ineligible between batches is not archived by a later batch).
  - A lock-ordering test: two concurrent invocations over overlapping row sets do not
    deadlock (real concurrency, `django_db(transaction=True)`), consistent with the
    `order_by("pk")` rule.
- *Gate:*
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/test_sweep_archive.py src/backend/apps/core/tests/test_sweep_lock_structure.py src/backend/apps/currencies/tests/test_recompute_command.py" test`
  then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk (highest):* resolving Q11 wrongly ships a batching fix that silently loses mutual
  exclusion between two concurrent sweeps. This is invisible in every existing test. The
  "acquired exactly once and held across all batches" test is the control.
- *Risk:* losing `order_by("pk")` during re-derivation and introducing a deadlock against a
  concurrent `ad_edit`.
- *Risk:* amending `test_sweep_lock_structure.py`'s `session is False` assertion and
  weakening it for **all 13** commands instead of the two. Constrain the amendment to the
  two named entries.
- *Risk:* the batch failure test being written as "everything rolls back" (the current
  behaviour), which would pass against the pre-fix code and prove nothing.
- *Rollback:* two commands plus test amendments. No schema. Rolling back restores the
  current all-or-nothing behaviour — safe, just slow.

---

### BLOCK 8 — Media promotion must not become visible before its row commits (DB-005)

| | |
|---|---|
| **Findings owned** | `03-DB-005` (**absorbs phase 01's `ENT-009`**) |
| **`depends_on`** | **BLOCK 6** (both edit `sweep_orphaned_media.py`, including `_STAGING_TTL_SECONDS`) |
| **Priority** | P2 (largest design in the phase; execute after BLOCK 6 has settled the TTL) |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- **Implementor — yes.** Always.
- **Auditor — yes.** The whole media storage contract must be mapped before the design is
  written: `STAGING_SUBDIR`, `STAGING_PREFIX`, `KEY_FORMAT_REGEX`, `move_staging_to_permanent`,
  `_collect_referenced_keys`, `_walk_media_files`, `_reclaim_stale_staging`, `_SEED_SUBDIR`,
  `delete_photo`, and `AdImage.save()`'s SHA-256 computation (which reads
  `MEDIA_ROOT / self.image` — so a staging key stored in the row is a **different path**).
- **Researcher — yes.** **Q7** and **Q8** are the phase's largest design question: where
  does the final move happen relative to the transaction boundary, and is the cheaper
  re-check variant actually safe?
- **Planner — yes.** The chosen design changes the **media directory contract** — a new
  excluded subdirectory plus a reclamation policy — which phases 07 and 13 also touch.
- **Validator — yes.** The block **rewrites a shipped green test that currently asserts the
  defect as intended**, and the failure mode of getting it wrong is *silent data loss for
  sellers* (a published listing permanently losing its photos).

#### 3.8.1 Decision gate — Q7 (where does the final move happen?)

**Phase 01 explicitly deferred this fork to phase 03** ("DB-005 owns the design decision,
*including the unresolved fork about where the final move happens relative to the
transaction boundary*") and **nothing in the tree pre-empts it.**

| Option | Change | Closes the window? | Test impact | Cost / future evolution |
|---|---|---|---|---|
| **A (report's preferred, architectural)** | Keep new files under a **new sweep-excluded subdirectory** until the owning `AdImage` row commits, then move them in an `on_commit` callback. | **Yes** — the file is invisible to `_walk_media_files` for its whole uncommitted life. | **Rewrites `test_save_photo_integration.py::TestSubmitAdStagingMove`** — both cases. `test_submit_ad_rollback_leaves_permanent_orphans` asserts permanent files **exist** after a rollback, staging files do **not**, and `AdImage.objects.filter(ad=ad).count() == 0`; its class docstring states the current ordering as *intended*. `test_submit_ad_moves_staging_to_permanent` must be re-derived too. | Requires: a new subdirectory constant in `filesystem.py`; a new exclusion in `_walk_media_files`; a **reclamation policy** for the new directory (files whose `AdImage` row rolled back must eventually be reclaimed — `_reclaim_stale_staging` is TTL-based and could be reused); a migration **only if** anything changes in the DB (it need not); and a check that `AdImage.save()`'s SHA-256 still finds the file and that the key stored in the row and the file's location stay consistent through the move. Changes the TX-then-FS pattern **in reverse** for this one case (an FS move *after* commit, which is fine, but the row and the file are briefly out of sync by design). |
| **B (cheaper, defence in depth)** | Keep the current promote-before-transaction ordering; **re-check each candidate orphan** inside a short transaction immediately before unlinking, and skip the file if a row now references it (deferring it to the next hourly run). | **No** — it narrows the window to a single re-check round-trip, and only if the re-check is inside the lock scope. | `test_delete_photo_called_within_lock_scope` asserts **every** `delete_photo` call happens while the lock is held — the re-check must stay inside it, or the test's premise changes. `TestSubmitAdStagingMove` stays green. | Costs a **transaction per candidate orphan**, for potentially thousands of orphans, inside a lock already held for the whole `os.walk`. Can **defer** a file a racing insert just claimed to the next hourly run. Much smaller diff, no contract change — which is both its main advantage and the reason it does not close the finding. |
| **C** | Do both: Option B as defence in depth **and** record Option A as the named follow-up. | Partially. | Both sets of test work. | Overlaps BLOCK 11-style bookkeeping. **Not recommended**: it ships half a fix and leaves the directory contract unwritten, which is exactly what phases 07/13 would fork on. |

**Q8 — the Researcher must additionally quantify** the realistic orphan count (which drives
the transaction-per-file cost of Option B), and state whether Option B is acceptable as a
complete fix or only as a stopgap.

**Findings and notes carried forward.**
1. **The problem, confirmed in the tree.** `submit_ad` promotes staged files to permanent
   `MEDIA_ROOT` **before** opening its `transaction.atomic()`, and only then inserts the
   `AdImage` rows inside that transaction. It never takes
   `AdvisoryLockId.SWEEP_ORPHANED_MEDIA` (103), so the write side and the sweep are never
   serialised. The hourly sweep takes a **point-in-time snapshot** of referenced keys,
   walks the whole `MEDIA_ROOT`, and deletes `on_disk - referenced` with **no re-check** at
   delete time. Any `AdImage` row created after the snapshot whose file is already promoted
   is classified as an orphan and unlinked.
2. **The exposure window is not a millisecond race** — it spans the entire `os.walk` of
   `MEDIA_ROOT`, minutes on a real media volume (volume-dependent; **not** re-measured,
   §0.2.4). The command also holds both the transaction and the sweep lock for the whole
   filesystem traversal.
3. **The current design is *documented* as intentional**, in two places: the
   `move_staging_to_permanent` docstring says the caller must run it **before**
   `transaction.atomic()` so a DB rollback leaves unreferenced orphans "rather than
   re-desynchronising the filesystem and database", and `TestSubmitAdStagingMove`'s class
   docstring says the same. **Both must change together with the code.** Per project rule 2
   the **tests** are what bend; the docstrings must be corrected, not preserved.
4. **`AD-003` (phase 05) must NOT be merged in.** It shares the symptom ("a DB row and a
   file can disagree") but has a different root cause — no refcount on shared storage keys,
   because `copy_ad` **reuses** storage keys while the `pre_delete` signal **deletes**
   unconditionally — and a different fix. BLOCK 8 must not remove `copy_ad`'s key reuse and
   must not add refcounting (§5.2).
5. **The directory-exclusion precedent is established** — `_SEED_SUBDIR = "seed"` and
   `STAGING_SUBDIR` are already skipped by `_walk_media_files`, and `filesystem.py` already
   owns the staging constants (`STAGING_SUBDIR`, `STAGING_PREFIX`). Option A follows that
   precedent rather than inventing a mechanism; it does **not** need a new pattern for
   "subdirectory that is never swept".
6. **`AdImage.save()` reads the file to compute a SHA-256** from
   `MEDIA_ROOT / self.image`. If Option A stores a key whose file still lives in the
   sweep-excluded subdirectory, `save()` computes a **different hash** than after the
   promotion move — silently corrupting the content-dedup key. This must be checked
   explicitly against `KEY_FORMAT_REGEX` and `AdImage.save()` before Option A is written.
7. **A migration is required only if the DB schema changes.** Option A should need none;
   Option B needs none. If a migration *is* generated, it is `media/0002_*` — check the
   directory immediately before generating (§5.3).

**Implementor task (`.ai\tasks\templates\task_template.yaml` shape).**

```yaml
id: task_03_b08_media_promotion_window
title: Close the window where a promoted file is visible to the orphan sweep before its AdImage row commits
priority: medium
depends_on: [task_03_b06_idle_timeout]
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 8 — Media promotion must not become visible before its row commits (DB-005)"
extra_context: |
  The final media-move location is a DECISION GATE (Q7) and must be closed before
  implementation. Options A/B/C are tabulated in the block's "Decision gate" section with
  their test and cost consequences. Do not begin implementation until the Researcher has
  recorded a choice. Do not merge AD-003 (phase 05) into this block.

description: >
  submit_ad promotes staged files to permanent MEDIA_ROOT before opening its
  transaction.atomic(), then inserts AdImage rows inside that transaction, without taking
  AdvisoryLockId.SWEEP_ORPHANED_MEDIA. A concurrent sweep_orphaned_media takes a
  point-in-time snapshot of referenced keys and unlinks referenced-key-less files across the
  whole os.walk, so a promoted file whose row is not yet committed is classified as an
  orphan and deleted. Apply the chosen design so no file is ever visible to the sweep
  before the row that owns it is committed.

goals:
  - eliminate the promote-before-row-commit window
  - do not introduce unbounded growth (files left behind must be reclaimed)
  - keep AdImage content dedup (SHA-256) stable across any promotion move
  - keep the TX-then-FS convention for every deletion

files:
  - path: src/backend/apps/ads/services/submission.py
    targets: [{ type: function, name: submit_ad }]
    semantic_anchors:
      insert_after: { type: function_call, value: "move_staging_to_permanent" }
  - path: src/backend/apps/media/services/filesystem.py
    targets:
      - { type: function, name: move_staging_to_permanent }
      - { type: module, name: filesystem }
    semantic_anchors: {}
  - path: src/backend/apps/media/management/commands/sweep_orphaned_media.py
    targets:
      - { type: function, name: _walk_media_files }
      - { type: function, name: _collect_referenced_keys }
      - { type: function, name: _reclaim_stale_staging }
      - { type: function, name: Command.handle }
    semantic_anchors: {}
  - path: src/telegram_bot/tests/test_save_photo_integration.py
    targets: [{ type: class, name: TestSubmitAdStagingMove }]
    semantic_anchors:
      replace_in_body:
        old: "the promote-before-transaction ordering is intended"
        new: "the file must not be sweep-visible before its row commits"
  - path: src/backend/apps/media/tests/test_sweep_orphaned_media.py
    targets: [{ type: class, name: TestSweepOrphanedMedia }]
    semantic_anchors: {}

changes:
  - action: add_code
    description: >
      Apply the Q7 decision. Option A: a new sweep-excluded subdirectory in filesystem.py,
      promoted to permanent storage in a transaction.on_commit callback after the owning
      AdImage row commits, plus a matching exclusion and reclamation rule in
      _walk_media_files. Option B: a re-check inside a short transaction immediately
      before each unlink, kept INSIDE the AdvisoryLockId.SWEEP_ORPHANED_MEDIA lock scope.
  - action: rewrite_docstring
    description: >
      Correct move_staging_to_permanent's "caller must run before transaction.atomic()" doc
      and TestSubmitAdStagingMove's class docstring, which currently document the defect as
      intended behaviour.
  - action: rewrite_test
    description: >
      Rewrite both cases of TestSubmitAdStagingMove to the chosen design: after a rolled-back
      submit no file exists in permanent storage; after a successful submit the file is
      permanent AND an AdImage row exists AND a concurrent sweep cannot unlink it.

acceptance_criteria:
  - a sweep overlapping a submit_ad never deletes a file whose AdImage row commits
  - files orphaned by a rolled-back submit are reclaimed within a bounded time
  - AdImage.save() produces the same content hash before and after any promotion move
  - the concurrency regression test is RED against the pre-fix code
  - test_sweep_orphaned_media.py's seed/staging/reclaim cases pass unchanged
  - uv run ruff check src/ exits 0 and uv run basedpyright src/ reports 0 errors
```

**File surface (semantic units).**
- `src/backend/apps/ads/services/submission.py` → `submit_ad` (the `move_staging_to_permanent`
  call site and its position relative to `transaction.atomic()`).
- `src/backend/apps/media/services/filesystem.py` → `STAGING_SUBDIR`, `STAGING_PREFIX`,
  `KEY_FORMAT_REGEX`, `move_staging_to_permanent`, `delete_photo`, `upload_photo`,
  `download_telegram_file`.
- `src/backend/apps/media/management/commands/sweep_orphaned_media.py` →
  `_SEED_SUBDIR`, `_walk_media_files`, `_collect_referenced_keys`,
  `_reclaim_stale_staging`, `_STAGING_TTL_SECONDS`, `Command.handle`.
  **Shared with BLOCK 6 — see §5.3.**
- `src/backend/apps/media/signals.py` → `delete_adimage_files_on_delete` (the reclamation
  half; reference only unless the design changes it).
- `src/telegram_bot/tests/test_save_photo_integration.py` → `TestSubmitAdStagingMove`
  (**both** cases rewritten).
- `src/backend/apps/media/tests/test_sweep_orphaned_media.py` →
  `test_delete_photo_called_within_lock_scope` (the re-check must stay inside the lock, or
  this test's premise must be amended explicitly), `test_staging_file_survives_sweep`,
  `test_fresh_staging_file_preserved`.
- `src/backend/apps/media/models.py` → `AdImage.save()` / `KEY_FORMAT_REGEX` (reference only).
- **Not touched:** `copy_service.py`'s storage-key reuse (`AD-003`, phase 05);
  `delete_draft`'s `storage_keys` (that path genuinely uses them);
  `sweep_drafts.py` (BLOCK 1 and BLOCK 6 own it).

**Tests required.**
- *Must be changed (rewritten, per project rule 2 — this is the block's core obligation):*
  `src/telegram_bot/tests/test_save_photo_integration.py::TestSubmitAdStagingMove`:
  - `test_submit_ad_rollback_leaves_permanent_orphans` currently asserts that after a
    rolled-back `submit_ad` the **permanent** files exist, the staging files do **not**, and
    `AdImage.objects.filter(ad=ad).count() == 0` — with the class docstring calling the
    promote-before-transaction ordering *intended*. Under Option A that becomes: after a
    rollback, **no** file exists in permanent storage, the new subdirectory **does** hold
    the file, and no `AdImage` row exists. The rewrite must state in its docstring **why**
    the old expectation encoded the defect.
  - `test_submit_ad_moves_staging_to_permanent` must be re-derived: after a **successful**
    `submit_ad`, the file must be in permanent storage **and** an `AdImage` row must exist,
    and it must be shown that a concurrent sweep running between the row commit and the
    promotion move **cannot** unlink the file.
- *Must be added:*
  - **The concurrency regression test** (Option A): a `sweep_orphaned_media` run
    overlapping a `submit_ad` never deletes a file whose `AdImage` row commits. Force the
    interleaving with a hook/barrier, not with sleeps. It must be **red against the
    pre-fix code**.
  - **The reclamation test** (Option A): files left in the new sweep-excluded subdirectory
    by a rolled-back submit are eventually reclaimed, so Option A does not leak storage
    forever. Without this, the fix trades data loss for unbounded growth.
  - **The dedup-key test** (Option A, per note 6): `AdImage.save()` produces the same
    content hash whether the file is read pre- or post-promotion.
- *Must keep passing unchanged:*
  `apps/media/tests/test_sweep_orphaned_media.py::test_seed_dir_is_excluded`,
  `::test_ad_referenced_file_survives`, `::test_orphan_file_deleted`,
  `::test_staging_file_survives_sweep`, `::test_stale_staging_file_reclaimed`,
  `::test_fresh_staging_file_preserved`; the `TestSavePhotoThumbnailsIntegration` class
  (thumbnail generation, untouched by this finding);
  `src/backend/apps/ads/tests/test_ad_image_dedup.py` if present.
- *Gate:*
  `.\Makefile.ps1 test-recreate` if a migration was generated, then
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/telegram_bot/tests/test_save_photo_integration.py src/backend/apps/media/tests/ src/backend/apps/ads/tests/test_submission.py" test`,
  then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk (highest):* rewriting `TestSubmitAdStagingMove` and **not** updating the class
  docstring, so the next reader inherits "promote before TX ⇒ orphans on rollback" as
  documented intent and reverts the fix. The docstring is part of the deliverable.
- *Risk (Option A):* the new sweep-excluded subdirectory becomes a **second**
  `staging/` and nobody reclaims it — trading data loss for unbounded storage growth. The
  reclamation test is the control.
- *Risk (Option A):* `AdImage.save()`'s SHA-256 changes across the promotion move (note 6),
  silently breaking content dedup. Checked explicitly.
- *Risk:* taking `SWEEP_ORPHANED_MEDIA` on the submit hot path (Option B's alternative) —
  that serialises **every** seller submission against an `os.walk` and would be a new
  availability incident. This is the strongest argument against locking the hot path, and
  the Researcher must confront it before Option B is chosen.
- *Risk:* BLOCK 6 also edits `sweep_orphaned_media.py`. Sequential Implementor handles it;
  BLOCK 8 must re-read `_STAGING_TTL_SECONDS` rather than assume.
- *Rollback:* the code and test changes are reversible. **A deployed Option A leaves files
  in a subdirectory that a rolled-back code version would then treat as orphans** — the
  rollback plan must include a one-off reclamation of that directory.

---

### BLOCK 9 — Serialise and de-duplicate immediate-alert delivery (DB-007)

| | |
|---|---|
| **Findings owned** | `03-DB-007` |
| **`depends_on`** | **BLOCK 5** (BLOCK 7 is a soft sibling; BLOCK 7 must land first if both are scheduled) |
| **Priority** | P3 — **latent** (`IMMEDIATE_ALERTS_ENABLED` defaults to `False`) |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Ordering decision.** BLOCK 7 before BLOCK 9. They share the daily/hourly
`notification-exhaustion` cluster (the code context notes "both findings 03-DB-007 and
03-DB-003 touch the notification-exhaustion path"), and BLOCK 7's `AdvisoryLockId` /
`test_sweep_lock_structure.py` work is the more structural of the two. Running BLOCK 7
first keeps BLOCK 9's changes concentrated in `apps/search`.

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- **Implementor — yes.** Always.
- **Auditor — yes.** Whether the "immediate-alerts path can double-send" activation
  precondition is *still* true after BLOCK 5/6/7/8 land must be re-verified — several of
  those blocks change transaction boundaries in the same neighbourhood. The Auditor must
  also confirm whether `IMMEDIATE_ALERTS_ENABLED` has been turned on anywhere.
- **Researcher — yes.** **Q9** is a genuine correctness question, not a style one: the
  code context shows `record_notifications` returns `len(ads)` ("not necessarily
  created") and `find_matching_saved_searches` has **no** `NOT EXISTS` filter, so the
  report's premise ("a concurrent re-publish runs the matcher twice") is a **hypothesis,
  not a demonstrated fact**.
- **Planner — yes.** The chosen option may require a **schema migration** plus a **state
  machine**, which is design work with a data-migration tail.
- **Validator — yes.** The block lands **behind a disabled feature flag**, so nothing in
  production exercises it; only an independent review catches a design error before the
  flag is enabled.

#### 3.9.1 Decision gate — Q9 (is the shared advisory lock the actual fix?)

| Option | Change | Closes the double-send? | Schema | Complexity | Shipping |
|---|---|---|---|---|---|
| **A** | **Minimal:** take `AdvisoryLockId.ALERT_DELIVERY_TASK` (9) in `deliver_immediate_alerts`, and have `send_alerts` reuse it (it already takes 9). | **Possibly, but unproven.** It serialises two *concurrent deliveries*, so if the double-send is caused by concurrency this is sufficient. §2.7 of the code context shows **no demonstrated path where two deliveries run concurrently** for the same ad: the trigger is `transaction.on_commit`, and `Ad.transition_to` is the only caller (the web/bot publish paths both go through it). The *real* duplication risk is the ad being **published twice in sequence** — which no lock can prevent. | None. | Low. | Can ship immediately. But shipping only A is **provably insufficient** for the stated defect: it does not address `find_matching_saved_searches`' missing `NOT EXISTS` filter or `record_notifications`' meaningless return value. |
| **B** | **Service-level (report's preferred):** a `delivered_by_immediate_alerts` boolean on `SavedSearchNotification`, set **only on the immediate path**, with `find_matching_saved_searches` filtered on `NOT EXISTS(delivered_by_immediate_alerts=True)`. The daily path is left alone, so its existing idempotency (phase 01's `fbbb6cf`) is untouched. | **Yes** — it makes the outcome a property of the **data**, not of lock timing. | **Yes**: `search/0003_*` adding a nullable boolean column. | Medium. | Should **not** ship before `IMMEDIATE_ALERTS_ENABLED` is enabled. A nullable boolean with backfill `NULL` is backward compatible (existing rows simply do not filter). |
| **C** | **Command-level (report's alternative):** `send_alerts` skips any `(saved_search, ad)` pair that has **any** existing notification row. | Closes **half** the problem (the daily path) but **misses** the immediate path entirely, because the immediate path writes the row itself. | None. | Lowest. | Ships now; **Option B is still required** for the immediate path. The report's own framing is that C is A + an extra step. |

**The Researcher must state which option it chose and why, and must answer this question
explicitly:** *does the shared advisory lock (A) close the reported double-send, and if not,
what does?* The plan does **not** answer it on the Researcher's behalf, because the code
context's own §2.7 analysis is unable to demonstrate a concurrency trigger and the
`on_commit` call site is unique. **A block that ships only A must record in its commit
message that the concurrency path is unproven and that B remains required.**

#### 3.9.2 Decision gate — Q10 (the delivery-state column)

If Option B is chosen, the Planner must specify before coding:
- the column's name, type, nullability and default — a **fixed value** must be an enum
  member or a named constant, not a bare boolean literal scattered across call sites
  (project rule 10);
- **who writes `True`**: only `deliver_immediate_alerts`, never `send_alerts`;
- **when**: inside the same transaction that creates the notification row, so the flag and
  the row commit together. Writing it after the send leaves a window where a crash loses
  the flag but keeps the message — the duplicate is *already sent*, so the flag must be
  written **before** dispatch;
- **backfill**: existing rows get `NULL` (they may or may not have been immediate-sent;
  guessing either way creates duplicates or silent gaps). A `NOT NULL DEFAULT false`
  backfill would be **wrong** — it would re-notify every previously immediate-sent pair.

#### 3.9.3 Findings and notes carried forward.
1. **The defect, confirmed in the tree.** `deliver_immediate_alerts` takes no advisory
   lock, opens no transaction, and calls `record_notifications(saved_search, [ad])`
   **before** `_executor.submit(_run_send, payloads)`. If a send fails the
   `SavedSearchNotification` row is already committed, so the daily `send_alerts` run
   **skips** that (search, ad) pair — a **silent alert loss**, which is the opposite of a
   duplicate and is arguably worse. This framing must be in the block's summary; the report
   frames the finding only as a double-send.
2. **`record_notifications` cannot be the duplicate detector.** It returns `count =
   len(ads)` — the number of rows *offered*, not created — and its own docstring says so.
   `test_alert_query.py::TestRecordNotifications::test_ignore_conflicts_skips_duplicates`
   must keep passing; it asserts the bulk_create call with `ignore_conflicts=True`.
3. **The pre-existing misleading test**, confirmed in the tree:
   `src/backend/apps/search/tests/test_alert_query.py::TestDeliverImmediateAlerts::test_records_notification_idempotently`
   does `with patch(f"{MODULE}._run_send"):` so the callback runs inline and the executor is
   bypassed — which means it does **not** actually test dispatch ordering. It asserts the
   immediate path creates a notification and suppresses the daily one. It does **not** pin
   the defect. Per project rule 2 it stays as-is unless the chosen option inverts it; if it
   does, rewrite it with a recorded rationale.
4. **The model exists in the tree.** `send_alerts.Command.handle` already treats lock 9
   as its critical section with `_notify_start`/`_notify_done` sentinels, and its docstring
   already nominates *"a delivery-state column on `SavedSearchNotification` (phase 03
   `DB-007`'s schema)"* as the correct fix. **That is the direction the tree points at.**
   The block may not contradict it, and phase 01 must not have added the column itself.
5. **`uqsavedsearchad` (q_saved_search_ad) is a unique index on `(saved_search, ad)`** —
   `record_notifications`' `ignore_conflicts=True` is therefore a true no-op backstop for
   concurrent creates of the *same* pair. It does **nothing** for Option B's
   "immediate sent ⇒ daily skips" filter, which needs its own column.
6. **The feature is latent.** `IMMEDIATE_ALERTS_ENABLED = env.bool(..., default=False)`
   in `config/settings/base.py`. The gate is checked by the `post_save` signal receiver, so
   the block's changes are exercised only when the flag is on. **The block's tests must
   exercise the code path directly**, not by flipping the setting globally.
7. **A bot pool hazard, not a defect.** `_executor` is a bounded module-level
   `ThreadPoolExecutor(max_workers=5)` in the **web** process; the bot process has its
   own. `asyncio.run` inside `_run_send` creates a fresh loop per batch and a fresh `Bot`
   per loop, with `finally: await bot.session.close()`. That is existing, working,
   deliberate behaviour. **Do not "fix" it** — out of scope (§6).

**Implementor task (`.ai\tasks\templates\task_template.yaml` shape).**

```yaml
id: task_03_b09_immediate_alert_serialisation
title: Serialise immediate-alert delivery and de-duplicate it against the daily digest
priority: medium
depends_on: [task_03_b05_lock_timeout, task_03_b07_per_batch_commit]
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 9 — Serialise and de-duplicate immediate-alert delivery (DB-007)"
extra_context: |
  Q9 and Q10 are DECISION GATES and must be closed before implementation. Options A/B/C
  are tabulated in the block's "Decision gate" sections with their consequences. Shipping
  Option A alone is permitted ONLY if the commit message records that the concurrency path
  is unproven and that Option B remains required. Do not revert phase 01's send_alerts
  idempotency work (fbbb6cf).

description: >
  deliver_immediate_alerts records SavedSearchNotification rows before dispatching the
  send, so a failed send permanently suppresses that pair in the daily send_alerts run, and
  a re-published ad re-runs the matcher with no exclusion filter. Apply the chosen option so
  a failed immediate send is retried by the daily path and an already-delivered pair is not
  delivered twice.

goals:
  - a failed immediate send must not permanently suppress the daily digest for that pair
  - an already-delivered pair must not be delivered twice
  - keep the daily path's phase-01 idempotency untouched
  - keep the IMMEDIATE_ALERTS_ENABLED gate and the bounded executor unchanged

files:
  - path: src/backend/apps/search/services/immediate_alerts.py
    targets:
      - { type: function, name: deliver_immediate_alerts }
      - { type: module, name: immediate_alerts }
    semantic_anchors: {}
  - path: src/backend/apps/search/services/alert_query.py
    targets:
      - { type: function, name: find_matching_saved_searches }
      - { type: function, name: record_notifications }
    semantic_anchors: {}
  - path: src/backend/apps/search/models.py          # Option B only
    targets: [{ type: class, name: SavedSearchNotification }]
    semantic_anchors: {}
  - path: src/backend/apps/search/migrations/0003_alter_savedsearchnotification.py   # Option B only
    targets: [{ type: module, name: migration }]
    semantic_anchors: {}
  - path: src/backend/apps/search/tests/test_alert_query.py
    targets:
      - { type: class, name: TestRecordNotifications }
      - { type: class, name: TestDeliverImmediateAlerts }
      - { type: class, name: TestImmediateAlertsGate }
    semantic_anchors: {}

changes:
  - action: add_code
    description: Apply the Q9/Q10 decision (advisory lock, delivered_by_immediate_alerts column, or both).
  - action: add_migration
    description: >
      Option B only: add a NULLABLE boolean column with NO backfill, written inside the same
      transaction that creates the notification row and BEFORE _executor.submit. Never
      NOT NULL DEFAULT false - that re-notifies every previously immediate-sent pair.
  - action: edit_docstring
    description: >
      Correct the immediate_alerts module docstring's claim that "ignore_conflicts" alone
      means the daily command never double-sends, and correct record_notifications' return
      of len(ads) if the chosen option changes its contract.

acceptance_criteria:
  - a failed _run_send followed by a send_alerts run still delivers the pair
  - a pair already delivered by the immediate path is not re-delivered by send_alerts
  - a pair delivered only by send_alerts is still excluded by the immediate matcher
  - pre-existing notification rows are NULL and are not filtered out
  - the feature still does nothing when IMMEDIATE_ALERTS_ENABLED is False
  - test_ignore_conflicts_skips_duplicates passes unchanged
  - .\Makefile.ps1 test-recreate run if search/0003_* was generated
```

**File surface (semantic units).**
- `src/backend/apps/search/services/immediate_alerts.py` →
  `deliver_immediate_alerts()`, the module docstring's idempotency claim, `_executor`,
  `_run_send`.
- `src/backend/apps/search/services/alert_query.py` → `find_matching_saved_searches()`,
  `record_notifications()` (its `count` return and its docstring).
- `src/backend/apps/search/models.py` → `SavedSearchNotification` (Option B only).
- **New (Option B only):** `src/backend/apps/search/migrations/0003_<change>.py`.
- `src/backend/apps/search/management/commands/send_alerts.py` →
  `Command.handle`'s docstring reference to "phase 03 `DB-007`'s schema" (Option C only
  touches the command's matching logic).
- `src/backend/apps/ads/signals.py` → the `post_save` receiver that gates on
  `IMMEDIATE_ALERTS_ENABLED` (reference only).
- **Not touched:** `send_alerts`'s daily-run marker / idempotency work from phase 01
  (`fbbb6cf`); `_build_payload`; `build_alert_message`; the bot's unsubscribe handler.

**Tests required.**
- *Must keep passing unchanged:*
  `test_alert_query.py::TestRecordNotifications::test_ignore_conflicts_skips_duplicates`;
  `test_alert_query.py::TestImmediateAlertsGate` (the flag gate); the phase-01
  `send_alerts` idempotency tests; `src/telegram_bot/tests/test_alerts*.py`.
- *Must be added:*
  - **The lost-alert regression test**: a failed `_run_send` followed by a `send_alerts`
    run must still deliver. **Red against the pre-fix code.**
  - **The duplicate-suppression test** (Option B): once the immediate path has delivered,
    a subsequent `send_alerts` run does **not** re-deliver the same (search, ad) pair;
    and the converse — a pair delivered **only** by `send_alerts` **is** still skipped by
    the immediate matcher (that is what `ignore_conflicts` already gives).
  - **The backfill test** (Option B): pre-existing notification rows carry
    `delivered_by_immediate_alerts = NULL` and are **not** filtered out.
  - A test that the immediate path still works when `IMMEDIATE_ALERTS_ENABLED` is
    `False` (the flag path must be unchanged).
- *Must be changed:* `TestDeliverImmediateAlerts::test_records_notification_idempotently`
  **only if** the chosen option inverts it, with a recorded rationale in its docstring.
- *Gate:*
  `.\Makefile.ps1 test-recreate` if `search/0003_*` was generated, then
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/search/tests/ src/backend/apps/ads/tests/ src/telegram_bot/tests/test_alerts.py" test`,
  then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk:* shipping Option A alone and recording the feature as fixed. The block summary
  must state that the concurrency path is unproven and that B remains required.
- *Risk (Option B):* writing the flag **after** the send — a crash then duplicates the
  message. The flag must be written **before** dispatch, in the same transaction as the
  row.
- *Risk (Option B):* a `NOT NULL DEFAULT false` backfill re-notifies every previously
  immediate-sent pair — a mass duplicate-send on first enable. The column must be nullable
  with no backfill.
- *Risk:* reverting the `send_alerts` docstring change from phase 01.
- *Rollback:* the column removal migration is reversible. **Rolling back after the flag is
  enabled means every pair already marked `True` becomes eligible again** — the rollback
  plan must include disabling `IMMEDIATE_ALERTS_ENABLED` first.

---

### BLOCK 10 — One single-draft policy, applied in both creators (DB-009)

| | |
|---|---|
| **Findings owned** | `03-DB-009` |
| **`depends_on`** | **BLOCK 4** (both blocks implement the same single-draft policy; BLOCK 4 establishes the rule for `create_draft_ad`) |
| **Priority** | P3 |
| **Roster** | **Implementor, Auditor, Planner, Validator** |

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — yes.** The finding's central correction is that `copy_ad` is called from
  exactly **one** production site (`telegram_bot/handlers/ad_copy.py::cmd_copy`, which
  `sync_to_async`s it) and there is **no** web route for it — the report's other source
  was a **test helper**. That must be re-verified at the anchor, along with the model's
  `status` default (BLOCK 4/10 both depend on it).
- **Researcher — no.** There is no external best-practice question. The choice is a
  **product** decision (Q12), not a technical survey.
- **Planner — yes.** The product rule must be specified for **both** creators at once, the
  error-handling boundary defined, and the i18n string set designed.
- **Validator — yes.** The change alters seller-visible behaviour and ships a new
  user-facing message; and the "unified rule" is only credible if both call sites are shown
  to obey it.

#### 3.10.1 Decision gate — Q12 (which product rule?)

| Option | Change | Seller experience | Compatibility | Risk |
|---|---|---|---|---|
| **A (report's recommendation)** | **"A new draft replaces the current one."** `copy_ad` deletes the user's existing `DRAFT` first — **exactly the pattern `create_draft_ad` already implements** — then creates. | Silent and forgiving: `/copy` always works, the previous draft's content is replaced. The seller is not asked anything. | Consistent with the shipped `create_draft_ad` policy; no new message needed. | The replaced draft's `AdImage` files are deleted by the `pre_delete` signal → **filesystem side effects must be after commit** (the `create_draft_ad` pattern already does this). |
| **B** | **"A second draft is rejected."** `copy_ad` catches `IntegrityError` from the unique constraint and the handler answers a new translated *"You already have a draft. Finish or delete it first."* | Explicit; the seller keeps their existing draft. | **Diverges** from `create_draft_ad`, which deletes. Unifying then requires changing `/post` too — a behaviour change on the busiest bot path. | A new i18n string (ru + bs required); `cmd_copy`'s current `except Exception` formatting the raw driver error must be replaced anyway. |
| **C** | Keep the current 500-ish behaviour and only **improve the error message** — catch `IntegrityError` in `copy_ad` and log it, re-raising a domain error the handler renders. | Same as today, better worded. | No policy change. | **Does not unify the rule**, which is the finding's actual ask, and the report explicitly recommends applying one rule in both creators. |

**The Planner must state which option it chose and must not implement C** — C addresses the
message without addressing the missing policy. **If the coordinator/user cannot be asked,
default to A** (it matches shipped behaviour and needs no new i18n) **and record that the
choice was made by default, not by decision** in the commit message.

**Findings and notes carried forward.**
1. **The raw error is user-visible today.** `cmd_copy`'s `except Exception` answers
   `_("Failed to copy ad: {error}").format(error=e)`, where `e` is the psycopg
   `IntegrityError`. The driver text (constraint name, `DETAIL Key (user_id, status)=…`,
   `CONTEXT  INSERT INTO ads`) is **interpolated into a Telegram message**. Whatever
   option is chosen, this broad formatter must stop surfacing raw exception text.
2. **`copy_ad` never sets `status=`.** It relies on the `Ad.status` model default
   (`AdStatus.DRAFT`). Adding an explicit `status=AdStatus.DRAFT` costs nothing and makes
   the intent legible — but it is a **cosmetic** change and must not be bundled as if it
   were the fix.
3. **Option A's ordering rule.** Read the existing DRAFT and delete it **before** creating
   the new one, matching `create_draft_ad`'s documented "Option D: delete + recreate".
   The **partial unique index** `uq_ads_single_draft_per_user` remains the backstop; if it
   fires, the retry path is BLOCK 4's shape (a savepoint), not a new mechanism.
4. **The user id comes from `tg_ctx.user.id`** in `cmd_copy`, not from a stored profile.
   A row left by a different Telegram account with the same `User` row is out of scope.
5. **`test_copy_ad.py`'s module docstring** already states the constraint correctly: *"The
   source ad must be in a non-DRAFT status because of the `uq_ads_single_draft_per_user`
   unique constraint — the seller cannot have an existing DRAFT when `copy_ad` runs."* That
   is the finding, written down, with no test guarding it. **The block's job is to make
   the docstring true**, either by adopting option A (the precondition becomes unnecessary)
   or by making the precondition explicit and enforced.
6. **`src/telegram_bot/tests/test_ad_copy.py`** asserts that the failure message contains
   `"failed"`. **That assertion must stay valid** under the chosen option — it is the
   cheapest guard that the handler still catches and still answers.

**File surface (semantic units).**
- `src/backend/apps/ads/services/copy_service.py` → `copy_ad()`, its docstring's `Raises:`
  section.
- `src/telegram_bot/handlers/ad_copy.py` → `cmd_copy()`'s exception handlers and the
  failure message.
- `src/backend/apps/ads/models.py` → `Ad.status` default and the
  `uq_ads_single_draft_per_user` `UniqueConstraint` (reference only).
- `src/backend/apps/ads/tests/test_copy_ad.py` → module docstring; a new policy test.
- `src/telegram_bot/tests/test_ad_copy.py` → the `"failed"` assertion (must keep passing).
- i18n: `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` (Option B only).
  **Shared artefact — §5.3.**
- **Not touched:** `cmd_post`'s existing draft replacement (BLOCK 4); the `copy_ad`
  storage-key reuse (`AD-003`, phase 05).

**Tests required.**
- *Must keep passing unchanged:* all of `src/backend/apps/ads/tests/test_copy_ad.py`'s
  field-copying assertions; `src/telegram_bot/tests/test_ad_copy.py` (including the
  `"failed"` assertion); `src/backend/apps/ads/tests/test_ad_constraints.py`.
- *Must be added:*
  - **The unified-policy test**: a seller with an existing `DRAFT` runs `/copy`, and the
    assertion matches the **chosen** option — under A, exactly one DRAFT remains and it is
    the copy; under B, the existing draft survives and the new message is returned.
  - **The constraint test**: the partial unique index still fires (unchanged).
  - A test that the failure message contains **no raw driver text** (no `Key (`, no
    `CONTEXT`, no `INSERT INTO`).
  - A test that the replaced draft's media files are removed **after** commit, not inside
    the transaction (Option A) — mirrors `create_draft_ad`'s `TestCreateDraftAdCrashRecovery`.
- *Gate:*
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/test_copy_ad.py src/telegram_bot/tests/test_ad_copy.py src/telegram_bot/tests/test_create_draft_ad.py src/backend/apps/ads/tests/test_ad_constraints.py" test`
  then `.\Makefile.ps1 test`.

**Risk / rollback.**
- *Risk:* Option A deleting the seller's in-progress draft **before** the copy is committed,
  so a later failure loses both. The delete and the create must be in one transaction, and
  the file deletions after commit.
- *Risk:* changing the error surface in a way that breaks `test_ad_copy.py`'s `"failed"`
  assertion.
- *Risk:* option C shipped by default ("just improve the message"), leaving the missing
  policy unaddressed. Explicitly forbidden above.
- **Rollback:** two small functions plus an i18n string. Fully reversible; no schema.

**Implementor task (`.ai\tasks\templates\task_template.yaml` shape).**

```yaml
id: task_03_b10_single_draft_policy
title: Apply one single-draft policy in both draft creators and stop leaking raw driver errors
priority: low
depends_on: [task_03_b04_create_draft_savepoint]
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 10 — One single-draft policy, applied in both creators (DB-009)"
extra_context: |
  Q12 is a PRODUCT decision gate. Option C is FORBIDDEN - it improves the message without
  addressing the missing policy. If no decision is available, default to Option A (it
  matches the shipped create_draft_ad behaviour and needs no new i18n) and record in the
  commit message that the choice was made by default, not by decision.

description: >
  copy_ad never sets status, never handles uq_ads_single_draft_per_user, and never touches
  an existing DRAFT. When a seller already has one, the constraint fires and cmd_copy's
  broad `except Exception` interpolates the raw psycopg IntegrityError text into a Telegram
  message. Apply the chosen single-draft policy in copy_ad, keep it identical to the one
  create_draft_ad implements, and stop surfacing raw exception text.

goals:
  - apply ONE single-draft policy across create_draft_ad and copy_ad
  - stop interpolating raw database exception text into user-facing messages
  - keep filesystem deletions after commit
  - keep the partial unique index as the backstop, not as the primary mechanism

files:
  - path: src/backend/apps/ads/services/copy_service.py
    targets: [{ type: function, name: copy_ad }]
    semantic_anchors:
      insert_after: { type: assignment, value: "new_ad = Ad(" }
  - path: src/telegram_bot/handlers/ad_copy.py
    targets: [{ type: function, name: cmd_copy }]
    semantic_anchors:
      replace_in_body:
        old: '_("Failed to copy ad: {error}").format(error=e)'
        new: '_("Failed to copy ad.")'
  - path: src/backend/apps/ads/tests/test_copy_ad.py
    targets: [{ type: module, name: test_copy_ad }]
    semantic_anchors: {}
  - path: src/telegram_bot/tests/test_ad_copy.py
    targets: [{ type: function, name: cmd_copy }]
    semantic_anchors: {}   # the "failed" assertion must keep passing; do not edit

changes:
  - action: add_code
    description: >
      Option A: delete the seller's existing DRAFT before creating the copy, inside the same
      transaction, exactly mirroring create_draft_ad's documented delete+recreate pattern.
      Option B: let the constraint fire and map IntegrityError to a new translated domain
      error with a seller-facing message.
  - action: edit_error_handler
    description: >
      Replace the raw-interpolating `except Exception` branch in cmd_copy with one that logs
      via logger.exception and answers a translated, non-interpolating message.
  - action: edit_docstring
    description: >
      Correct copy_ad's docstring and test_copy_ad.py's module docstring, which currently
      state the single-draft precondition as a fact the code does not enforce.

acceptance_criteria:
  - a seller with an existing DRAFT running /copy ends with exactly one DRAFT (Option A) or
    keeps the old one and receives the translated message (Option B)
  - the failure message contains no raw driver text (no "Key (", no "CONTEXT", no "INSERT INTO")
  - a replaced draft's media files are removed after commit, not inside the transaction
  - test_ad_copy.py's "failed" assertion passes unchanged
  - uv run ruff check src/ exits 0 and uv run basedpyright src/ reports 0 errors
```

---

### BLOCK 11 — Finding-ID namespace disambiguation (VAL-001)

| | |
|---|---|
| **Findings owned** | `03-VAL-001` (the source-comment half) |
| **`depends_on`** | *(none)* — executes last; re-reads every file it touches |
| **Priority** | P2 — **gated on a coordinator decision** |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- **Implementor — yes.** Always.
- **Auditor — yes.** The set of ambiguous citations must be re-derived at the anchor
  (68 matches across 26 files at `4fd8bd0`), and **which cycle each legacy ID belongs to**
  must be established from the audit history — that is an archival investigation, not a
  grep.
- **Researcher — yes.** **Q14's second half is a conventions question**: what is the
  maintainable way to cross-reference an ephemeral, per-cycle identifier in code comments
  so that the reference is unambiguous, durable, and does not require archaeology to
  resolve. The repository already contains one precedent (`03-DB-002`).
- **Planner — yes.** It touches **26 files across `apps/` and `telegram_bot/`** and sets a
  convention that **phases 04–15 are being written against in parallel right now**. Getting
  it wrong multiplies across twelve more phases.
- **Validator — yes.* The block's value is that a *future* reader is not misled. That is a
  judgement about reviewer experience, not something inspection can confirm.

#### 3.11.1 Decision gate — Q14, second half (coordinator decision required)

**The problem, verified at `4fd8bd0`:** 68 shipped citations across 26 files. Bare `DB-001`
through `DB-010` are used for **previous cycles'** defects, and this cycle's `DB-004`,
`DB-007` and `DB-010` are cited **naming-collision-identically**. `advisory_lock.py` is the
worst case: a three-line comment cites *"phase 03's `DB-004`"* and *"see `DB-010`"* — and
three lines above, the same file says *"removed in `DB-007`"* for a different cycle's
`DB-007`. A grep for `DB-010` is ambiguous **within one file**. Phase 01 made it worse by
adding the first two citations.

| Option | Change | Cost | Durability | Verdict |
|---|---|---|---|---|
| **A** | **Prefix-only.** Mandate `NN-DB-00N` for every **new** citation; leave the 68 legacy ones untouched. | ~0 files. | The problem persists and keeps growing: every phase adds bare IDs, and the ambiguity doubles. Does not fix the two files this cycle already polluted. | **Rejected** — it stops the bleeding without treating the wound, and it leaves the two worst offenders unaddressed. |
| **B** | **Prefix sweep.** Prefix every one of the 68 legacy citations with the cycle they belong to, determined from the audit history. | 26 files. Requires archaeology: the previous cycles' reports are partly **deleted from the working tree** (`03-DB-001`/`002`/`003`/`004`/`007`/`010` are referenced by files whose original report may not exist). | Durable while cycles keep adding. **Weak where the audit history is missing**, producing confident-but-wrong cycle attributions — arguably worse than today's honest ambiguity. | **Risky** as a blanket sweep. Viable as a **targeted** sweep for the handful of files where a wrong reader is actively harmful (production code, not tests). |
| **C (Planner's recommendation)** | **Descriptive replacement.** Rewrite the legacy citations to describe the defect instead of citing an opaque id — *"the autocommit-release bug"*, *"the max_ads_per_user TOCTOU"*, *"the archive_sweep lost-update race"* — and reserve the `NN-DB-00N` form exclusively for **defects in the current remediation cycle**. Where a cross-reference is genuinely needed, name the **symbol and the test** that guards the fix (`the fix for the lost-update race guarded by test_sweep_archive.py::TestArchiveSweepRowLockConcurrency`). | 26 files, same file count as B, but each edit is self-contained and needs no archaeology. | **The most durable** of the three: a description cannot become ambiguous when a new cycle reuses an id. | **Recommended** — but it changes what the comments *are*, and it touches files outside phase 03's findings. **Coordinator decision required.** |

**Whatever is chosen, the following are already decided and are not up for renegotiation:**
- This plan, and every phase from 04 onwards, keys its tracker on **`NN-<PREFIX>-00N`**
  (§5.2). The precedent is shipped: `src/telegram_bot/tests/test_unsubscribe.py` already
  cites `03-DB-002`.
- **Every comment phase 03 adds** in BLOCK 1 – BLOCK 10 uses `03-DB-00N`. BLOCK 2 has
  already normalised the two this-cycle citations in `advisory_lock.py` as part of its own
  work.
- BLOCK 11 does **not** touch any code file it has no other business touching. It may
  correct a citation **in a file it already opened** (BLOCK 2 did this for
  `advisory_lock.py`) without returning to this gate.

**Findings and notes carried forward.**
1. **The blast radius is real and already shipped.** `src/backend/apps/ads/models.py`,
   `src/backend/apps/ads/services/submission.py`, `src/backend/apps/ads/views/edit.py`,
   `src/backend/apps/moderation/admin_actions.py`,
   `src/backend/apps/moderation/services/moderation_log.py`,
   `src/backend/apps/core/utils/advisory_lock.py`,
   `src/backend/apps/core/management/commands/archive_sweep.py`,
   `src/backend/apps/search/management/commands/send_alerts.py`, and `src/telegram_bot/services/ad_data/orm.py`
   all carry ambiguous ids in **production** code. The rest are in tests.
2. **This cycle's own ids are already in production code** — `advisory_lock.py` (DB-004,
   DB-010) and `send_alerts.py` (DB-007, shipped by phase 01). These are the highest-value
   three and are **not** optional under any option: they must be disambiguated even if the
   coordinator de-scopes the legacy sweep.
3. **Test files are lower priority than production files.** A misleading test docstring
   costs a future maintainer some time; a misleading production comment costs them
   debugging time. If the block is de-scoped for budget, **de-scope test files first**.
4. **`git blame` / the audit history is the only evidence for a cycle number.** Do **not**
   infer one. If it cannot be established, Option C (descriptive) is the correct fallback,
   because it needs no attribution.
5. **Phases 01 and 02 have already set local precedents** that this block should not
   silently overwrite: phase 01's `7aac8d3` comment in `advisory_lock.py` and phase 02's
   `VAL-001`-scoped changes. Re-read rather than assume.

**File surface (semantic units).**
- Every file under `src/` containing a `DB-0\d\d` citation, re-derived by the Auditor.
  Production files first: `apps/core/utils/advisory_lock.py`,
  `apps/core/management/commands/archive_sweep.py`,
  `apps/ads/models.py`, `apps/ads/services/submission.py`, `apps/ads/views/edit.py`,
  `apps/moderation/admin_actions.py`, `apps/moderation/services/moderation_log.py`,
  `apps/search/management/commands/send_alerts.py`,
  `telegram_bot/services/ad_data/orm.py`.
- **No behavioural change.** Comments and docstrings only. **No test file's assertions may
  change.**

**Tests required.**
- *None new.* A comment-only block cannot have a behavioural test, and writing one would be
  testing trivia. The gate is:
  - `.\Makefile.ps1 test` — the full suite must be green, proving nothing functional moved;
  - `uv run ruff check src/` and `uv run basedpyright src/` — green;
  - a re-derivation sweep showing **zero remaining** bare `DB-0\d\d` citations that this
    block was scoped to cover.
- If the block is de-scoped, §8.2's ID-sweep line is re-baselined and §6 records what was
  left.

**Risk / rollback.**
- *Risk:* rewriting a comment in a file **another phase is editing right now**, causing a
  merge conflict or a clobbered edit. The Implementor must re-read each file immediately
  before editing and stage explicit paths.
- *Risk:* attributing the wrong cycle (Option B). **Mitigation: prefer Option C's
  descriptive form wherever attribution is uncertain.**
- *Risk:* an implementer "helpfully" also renames tests or assertions. Explicitly
  forbidden — **assertions are immutable in this block**.
- *Risk:* the block is treated as cosmetic and de-scoped entirely, leaving the three
  production citations from note 2 ambiguous. Those three are non-negotiable.
- *Rollback:* comment-only; fully reversible.

**Implementor task (`.ai\tasks\templates\task_template.yaml` shape).**

```yaml
id: task_03_b11_finding_id_disambiguation
title: Disambiguate finding-id cross-references in comments and docstrings
priority: medium
depends_on: []
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 11 — Finding-ID namespace disambiguation (VAL-001)"
extra_context: |
  This block is GATED on a coordinator decision (Q14 second half, §3.11.1). Options A/B/C
  are tabulated with cost and durability. ASSERTIONS ARE IMMUTABLE - comment and docstring
  text only, never a test name, never an assertion. Non-negotiable minimum: the three
  production citations this cycle already polluted (advisory_lock.py DB-004 and DB-010,
  send_alerts.py DB-007) must be disambiguated under ANY option.

description: >
  68 shipped citations across 26 files use bare DB-00N ids for previous cycles' defects,
  while this cycle's DB-004, DB-007 and DB-010 are cited naming-collision-identically.
  advisory_lock.py cites both a previous cycle's DB-010 and this cycle's DB-004 within
  three lines. Apply the chosen disambiguation so a future reader is not misled, and so
  the NN-DB-00N convention is unambiguous going forward.

goals:
  - disambiguate every in-scope citation without asserting a cycle number that cannot be evidenced
  - reserve the NN-DB-00N form for the current remediation cycle
  - touch production files before test files
  - change no behaviour and no assertion

files:
  - path: src/backend/apps/core/utils/advisory_lock.py            # production, first
    targets: [{ type: function, name: advisory_lock }, { type: module, name: advisory_lock }]
    semantic_anchors: {}
  - path: src/backend/apps/core/management/commands/archive_sweep.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors: {}
  - path: src/backend/apps/ads/models.py
    targets: [{ type: class, name: Ad }, { type: function, name: transition_to }]
    semantic_anchors: {}
  - path: src/backend/apps/ads/services/submission.py
    targets: [{ type: function, name: submit_ad }]
    semantic_anchors: {}
  - path: src/backend/apps/ads/views/edit.py
    targets: [{ type: function, name: ad_edit }]
    semantic_anchors: {}
  - path: src/backend/apps/moderation/admin_actions.py
    targets: [{ type: class, name: ModerationAdminActions }]
    semantic_anchors: {}
  - path: src/backend/apps/moderation/services/moderation_log.py
    targets: [{ type: module, name: moderation_log }]
    semantic_anchors: {}
  - path: src/backend/apps/search/management/commands/send_alerts.py
    targets: [{ type: class, name: Command }]
    semantic_anchors: {}
  - path: src/telegram_bot/services/ad_data/orm.py
    targets: [{ type: function, name: create_draft_ad }]
    semantic_anchors: {}
  # plus every remaining file re-derived by the Auditor that contains a DB-0\d\d citation

changes:
  - action: edit_comment
    description: >
      Option C (recommended): replace opaque ids with a description of the defect, or name
      the symbol and test that guard the fix. Option B: prefix with the cycle, only where
      attribution is evidenced by the audit history - never inferred.
  - action: edit_docstring
    description: >
      Test-file docstrings may be rewritten; TEST NAMES AND ASSERTIONS MAY NOT. Files another
      phase is editing concurrently must be re-read immediately before editing and staged
      by explicit path.

acceptance_criteria:
  - zero remaining ambiguous citations among the files this block was scoped to cover
  - the three this-cycle production citations are disambiguated under any option
  - no test name and no assertion was changed (the full suite proves it)
  - no behaviour changed: .\Makefile.ps1 test green, ruff and basedpyright green
  - no file was clobbered from a concurrent phase's uncommitted edit
```

---

## 4. Dependency graph

### 4.1 Execution order

```
BLOCK 1  DB-011    Remove redundant AdImage key pre-collection (6 sweeps)   deps: —
     │     ──► soft edge to BLOCK 6 (same file: sweep_drafts.Command.handle)
BLOCK 2  DB-010    Advisory-lock release log on the rollback path           deps: —
     │     ──► soft edge to BLOCK 11 (advisory_lock.py)
BLOCK 3  DB-002    record_event must not abort the caller's transaction      deps: —
     │     ══► HARD edge (03-VAL-002): BLOCK 5
BLOCK 4  DB-001    Recoverable race backstop in create_draft_ad             deps: — [GATED: 03-VAL-003 ack]
     │     ══► HARD edge: BLOCK 10
BLOCK 5  DB-004    Bound the lock wait + retry boundary (timeout half)      deps: BLOCK 3
     │     ├──► HARD edge: BLOCK 7   (both rewrite archive_sweep / recompute handle)
     │     └──► HARD edge: BLOCK 9   (shared ALERT_DELIVERY_TASK lock surface)
BLOCK 6  DB-003    Idle-timeout semantics for drafts (heartbeat+migration)  deps: BLOCK 1 (soft)
     │     ══► HARD edge: BLOCK 8   (both edit sweep_orphaned_media.py + _STAGING_TTL_SECONDS)
BLOCK 7  DB-008    Per-batch commit, advisory lock held once                deps: BLOCK 5
BLOCK 8  DB-005    Media promotion must not precede its row commit          deps: BLOCK 6
BLOCK 9  DB-007    Serialise + de-duplicate immediate-alert delivery        deps: BLOCK 5, BLOCK 7 (order)
BLOCK 10 DB-009    One single-draft policy in both creators                 deps: BLOCK 4
BLOCK 11 VAL-001   Finding-ID namespace disambiguation                      deps: — [GATED: Q14 decision]
```

**Safe serial order:** `1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11`.

Exactly one Implementor runs at a time, so the order is always serial. The DAG below
records the edges that would matter if a coordinator ever ran two Implementors in
parallel, and — more importantly — **the edges that mean a block must not be started
before another has landed**.

### 4.2 Why each edge exists

| Edge | Kind | Reason |
|---|---|---|
| **3 → 5** | **HARD — `03-VAL-002`** | A `statement_timeout` produces exactly the class of server-side `OperationalError` that `record_event`'s bare `except Exception` swallows and that aborts the caller's transaction. Shipping BLOCK 5 first turns DB-002 from *latent* into *live*. This is the single most important ordering constraint in the phase. |
| **5 → 7** | **HARD** | BLOCK 7 rewrites `archive_sweep.Command.handle` and `recompute_normalized_prices.Command.handle`. Under either option in BLOCK 5's Q1 table, the timeout mechanism lands in those same functions. Two blocks re-editing the same function body in one commit sequence is a merge hazard, and BLOCK 7's design must know which timeout convention exists so it can reuse rather than invent a second one. |
| **5 → 9** | **HARD** | `AdvisoryLockId.ALERT_DELIVERY_TASK` (9) is the surface BLOCK 9 operates on, and BLOCK 5 defines the bounded-wait behaviour that lock acquisition will inherit. Shipping BLOCK 9 first would mean re-visiting its transaction boundary after BLOCK 5 lands. |
| **6 → 8** | **HARD** | Both blocks edit `sweep_orphaned_media.py` — `_STAGING_TTL_SECONDS` (BLOCK 6's Q6) and `_walk_media_files` / `_reclaim_stale_staging` / `_SEED_SUBDIR` (BLOCK 8's Q7). BLOCK 8's reclamation policy for any new sweep-excluded subdirectory must be designed **against the TTL BLOCK 6 chose**, not against the stale value. Reversing this order means re-designing the reclamation rule. |
| **7 → 9** | **HARD (ordering only)** | No correctness dependency — they touch different apps (`core`/`currencies` vs `search`). The edge exists because BLOCK 7's `test_sweep_lock_structure.py` amendment and BLOCK 9's `AdvisoryLockId` usage are the same shared-artefact neighbourhood, and BLOCK 7 is the more structural of the two. Sequencing BLOCK 7 first keeps BLOCK 9's diff concentrated in `apps/search`. |
| **4 → 10** | **HARD** | Both blocks implement **one** single-draft policy. BLOCK 4 establishes what that policy is for `create_draft_ad` (delete-then-recreate, with a savepoint backstop). BLOCK 10 must apply the *same* policy in `copy_ad`; landing it first would mean writing the rule twice and then reconciling. |
| **1 → 6** | **SOFT** | BLOCK 1 removes the `storage_keys` comprehension from `sweep_drafts.Command.handle`; BLOCK 6 changes the *predicate* in the same function. The single Implementor handles it either way, but BLOCK 6 must re-read the file rather than assume BLOCK 1's state. Listed as an ordering preference, not a blocker. |
| **2 → 11** | **SOFT** | BLOCK 2 already normalises this cycle's two citations in `advisory_lock.py` as part of its own work (note: it must **not** touch the legacy `DB-001`/`DB-007` citations). BLOCK 11 runs last and re-reads the file. If BLOCK 11 is de-scoped, the three non-negotiable production citations in note 2 of that block still get handled — two of them by BLOCK 2, leaving only `send_alerts.py`. |

### 4.3 No edge exists for these, and why

- **BLOCK 1 and BLOCK 2 have no dependencies and are order-free with respect to each
  other.** Different files, no shared artefact, both pure-low-risk. They are sequenced only
  because a single Implementor runs sequentially.
- **BLOCK 3 and BLOCK 4 have no edge.** They are the two "small local fix" blocks in
  different apps (`apps/core/services/analytics.py` vs
  `telegram_bot/services/ad_data/orm.py`). BLOCK 3 gates BLOCK 5; BLOCK 4 gates BLOCK 10;
  the two chains are otherwise independent and could run in either order.
- **BLOCK 11 has no dependency** and is listed **last** purely so it can be de-scoped as a
  single decision at the end of the phase rather than interrupting the work. It re-reads
  every file it touches anyway, so ordering it last is strictly better for it.
- **BLOCK 6 does not depend on BLOCK 5.** Both change retention behaviour but neither's
  correctness depends on the other. BLOCK 6 does not introduce a lock wait of its own — the
  bot heartbeat is a single-column `UPDATE` with no `select_for_update`. If the coordinator
  wants to parallelise later, `6 → 8` is the only chain that must stay intact.
- **BLOCK 9 does not depend on BLOCK 6 or BLOCK 8.** They touch `apps/search` and
  `apps/ads`/`apps/media` respectively and share only the general "notification-exhaustion"
  neighbourhood noted in the code context — not a file, not a lock id, not a test.

### 4.4 The two gates that stop the DAG

Two blocks are **gated on a decision outside the implementation**, and neither gate is an
investigation:

| Gate | Blocks | Owner | Effect if the gate never closes |
|---|---|---|---|
| `03-VAL-003` acknowledgement — `AD-005` (phase 05, HIGH) and `03-DB-001` (this cycle, MEDIUM) are one defect filed twice. | BLOCK 4 | Coordinator | BLOCK 4 ships the single work item at MEDIUM regardless; the phase-05 re-rating is simply never recorded. **This gate is advisory and should not block the phase.** |
| `Q14` — the source-comment half of `03-VAL-001`. | BLOCK 11 | Coordinator | BLOCK 11 is de-scoped entirely and recorded in §6. The three production citations that this cycle already polluted must still be disambiguated — two are handled inside BLOCK 2, `send_alerts.py` is then handed to the coordinator. |

Every **other** gate in this plan (Q1–Q12) is a *technical* decision owned by the
Researcher/Planner inside the block itself and must be closed **before implementation
starts**, not before the phase starts.

---

## 5. Cross-phase coordination

Phases 01 and 02 are executed or in flight; **phases 04–15 are being planned in parallel
right now** by other Planner agents. This section is the boundary contract. It is
deliberately one-directional — phase 03 states what it owns and what it will not touch; it
does **not** attempt to coordinate with the other agents.

### 5.1 What phase 01 already owns and phase 03 must not re-ship

| Phase 01 artefact | What phase 03 must not do | Boundary |
|---|---|---|
| **`ENT-006` residual**, shipped in `7aac8d3`: the `migrate_locked` module docstring now states that a contending run **blocks**, and `advisory_lock`'s session branch emits `"Requesting session advisory lock %s"` **before** acquisition. | BLOCK 5 must add **no** timeout wording to `advisory_lock.py` and must **not** re-touch `migrate_locked.py`. `DB-004`'s implementation is the **timeout half only**. | `test_migrate_locked.py::TestSessionLockLogging::test_session_lock_logs_request_before_acquire` is now a hard regression guard and must stay green unchanged. Phase 01 also **forbade** touching the transaction branch's `on_commit` flow — BLOCK 2 is where that ban is lifted. |
| **`ENT-009`** (a draft's photos must be safely retained across the idle window; no time-based deletion). | BLOCK 6 must not re-solve it. It is **absorbed**: BLOCK 6's idle-semantics change *is* the implementation. | The two must not be filed as two work items in the final report. |
| **`ENT-009` sub-item** — no bot watchdog timer was added. | BLOCK 6 must **not** introduce a `DefaultBotProbe`-based watchdog as a *retention* mechanism; a heartbeat (a DB write) is the chosen shape. | The `probe` hook is a phase-01 mechanism with a different purpose. |
| **Phase 01 BLOCK 6** — `send_alerts` daily-run idempotency / liveness (`fbbb6cf`). | BLOCK 9 must **not** re-do it and must not revert its docstring change. The column `send_alerts`'s docstring nominates ("phase 03 `DB-007`'s schema") is **phase 03's to create**, but the daily path's existing behaviour is phase 01's. | The boundary is Option C in BLOCK 9's gate. |
| **Phase 01 BLOCK 8** — `advisory_lock` hardening that **deliberately left** the `session=False` branch's `on_commit` flow alone and used `test_advisory_lock_release_log.py` as the tripwire. | BLOCK 2 **is** that tripwire's owner now. It must rewrite the two tests, and it must be explicit in its commit message that this is the change phase 01 deferred. | Same file, sequential history. |
| **Phase 01 BLOCK 2** (`docker-compose.dev.override.yml`), BLOCK 1/4 (`ci.yml`), BLOCK 5/6/7/9 (`config/settings/**`, `.env.*.example`). | BLOCK 5 (Q1 Option A) may touch `base.py` and the four env templates. It must **re-read them immediately before editing** and never clobber a phase-02 edit. | §5.3. |

### 5.2 What phase 03 must not do, for other phases' sake

| Other phase | What phase 03 must not do | Boundary |
|---|---|---|
| **Phase 02 — `CFG-005` / `CFG-008` / `CFG-009`** | BLOCK 5 must not edit `base.py`'s `ALLOWED_ENV_VARS` grouping, the `read_env()` skip condition, or the secret guards; must not edit `prod.py`'s transport pins; must not rewrite `.env.example`'s header. Under Q1 Option A a **new** env var must land **with** its allowlist entry and its four template updates in one commit — and it must satisfy phase 02 BLOCK 6's reverse-direction consumed↔allowlist test when that lands. | `base.py` + `.env.*.example` are the phase's most contended files after `conftest.py`. |
| **Phase 04 — `AUT-007`** | Nothing. No interaction. | — |
| **Phase 05 — `AD-003`** (refcount on shared storage keys, because `copy_ad` reuses keys while `pre_delete` deletes unconditionally). | BLOCK 8 must **not** add refcounting, must **not** remove `copy_ad`'s storage-key reuse, and must not change `delete_adimage_files_on_delete`. `AD-003` shares DB-005's symptom and has a different root cause and a different fix. | BLOCK 8's Option A changes the *promotion window*, not the *sharing* semantics. |
| **Phase 05 — `AD-005`** ≡ `03-DB-001` (`03-VAL-003`) | Phase 05 must **not** ship a second patch. Phase 03 ships **one** work item at **MEDIUM** and escalates the re-rating (§5.4). BLOCK 4's fix must be the fix phase 05 adopts if it acts at all. | The same defect, one commit, one severity. |
| **Phase 06 — `PII-104`** (alert audience ignores consent / account state). | BLOCK 9 must **not** change the **recipient-selection** logic. Phase 03 owns the **delivery-state contract** (what has already been sent); phase 06 owns **who is eligible**. | `find_matching_saved_searches` is the boundary file — it is named in `PII-104`'s own list as excluded. If phase 06 edits it, BLOCK 9 must re-read. |
| **Phase 07 (media) / Phase 13 (performance)** | Both may touch `sweep_orphaned_media.py` and `filesystem.py`. BLOCK 8's **directory contract** (the sweep-excluded subdirectories and their reclamation rules) is recorded in §5.3 so those phases extend it rather than fork it. BLOCK 8 must not pre-empt a phase-07 media-model change. | BLOCK 8's design decisions are this plan's most portable output. |
| **Phase 11 (test coverage)** | The rewritten tests in BLOCK 2, 3 (Option B), 6, 8, 9 and 10 are **incidental rewrites required by a behaviour change**, not coverage improvements. Phase 11 must not claim them, and phase 03 must not expand them into new coverage while rewriting them. | A rewrite that grows into new coverage raises the regression risk of the block. |
| **Phase 12 (production-ops)** | The `bandit` / `gitleaks` verification gaps phase 02 recorded (`VAL-005`/`VAL-006`) are phase 12's. Phase 03 introduces no secrets and no shell scripts, but its new tests must still be written bandit-clean (list-form `subprocess` calls, no literal `/tmp`) so a future `VAL-006` fix does not redden CI. | Phase 02 §5.4. |
| **Phase 14 (i18n)** | BLOCK 6 and BLOCK 10 add user-visible strings. `src/backend/locale/*/LC_MESSAGES/django.po` is **shared** — both must append rather than regenerate, and neither may run a wholesale `makemessages` that discards a concurrent phase's additions. | §5.3. |

**The convention phases 04–15 must adopt (decided — `Q14`, first half):**

1. **This plan and every later plan keys its tracker on `NN-<PREFIX>-00N`** — for example
   `03-DB-002`, `15-AUT-001`. The precedent is already shipped:
   `src/telegram_bot/tests/test_unsubscribe.py` cites `03-DB-002`.
2. **A bare `DB-00N` / `CFG-00N` in a comment or docstring is unresolvable** and must not
   be written by a new phase. New cross-references use the cycle-scoped form.
3. **Phases 04–15 must not start BLOCK 11-style legacy sweeps of their own.** One
   sweep, in BLOCK 11, under the coordinator's chosen option — otherwise twelve phases
   rewrite the same 26 files differently and the convention is unenforceable.
4. **A plan document that cites a previous cycle's finding must say so in words** ("the
   phase-01 `ENT-006` fix"), never by bare id.

### 5.3 Shared-artefact reservations

| Artefact | Claimed by | Risk and rule |
|---|---|---|
| **`src/backend/conftest.py`** | Phase 03 **must not edit it at all** | The most contended file in the repository. `create_test_ad()` never sets `created_at` or `updated_at` (both `auto_*`), which is precisely why BLOCK 6's two tests must back-date **locally**. BLOCK 6 changes the two test files, not the helper. |
| **`AdvisoryLockId`** (`src/backend/apps/core/enums.py`) | **Phase 03 allocates no new member.** BLOCK 7 reuses `ARCHIVE_SWEEP` (1) and `RECOMPUTE_NORMALIZED_PRICES` (12) with `session=True`; BLOCK 9 reuses `ALERT_DELIVERY_TASK` (9); BLOCK 8 does **not** lock the submit hot path (that is the strongest argument against Option B). | 18 members today; ID 10 reserved (was `QUEUE_PROCESSING`, removed by a previous cycle's `DB-007`). If a design in BLOCK 7/8/9 concludes a new id is unavoidable, **all three** of `enums.py`, the lock-allocation table in `advisory_lock.py`'s module docstring, and `test_advisory_lock_ids.py` change in one commit — and the coordinator is told before, not after. |
| **`config/settings/base.py`** | BLOCK 5 (`DATABASES`, both branches; possibly a new timeout setting + its `ALLOWED_ENV_VARS` entry) | Concurrent with phase 02 BLOCKs 5 and 6. Re-read immediately before editing; never `git add .`. |
| **`.env.example`, `.env.dev.example`, `.env.prod.example`, `.env.test.example`** | BLOCK 5 (Q1 Option A only) | Concurrent with phase 02 BLOCK 6. `.env.example` also carries a UTF-8 BOM that phase 02 removes — **do not** re-add it. |
| **`src/backend/apps/core/utils/advisory_lock.py`** | BLOCK 2 (release-log fix + this-cycle re-citation), BLOCK 11 (legacy sweep, if not de-scoped) | BLOCK 2 must **not** rewrite the legacy `DB-001`/`DB-007` citations — BLOCK 11's chosen option may change the shape of that rewrite. |
| **`sweep_drafts.py`** | BLOCK 1 (key collection), BLOCK 6 (predicate + `updated_at`) | Soft edge (§4.3). BLOCK 6 re-reads. |
| **`sweep_orphaned_media.py`** | BLOCK 6 (`_STAGING_TTL_SECONDS`), BLOCK 8 (`_walk_media_files`, `_reclaim_stale_staging`, `_SEED_SUBDIR`) | Hard edge `6 → 8` (§4.2). BLOCK 8's reclamation policy must be designed against BLOCK 6's chosen TTL. Also shared with phases 07/13. |
| **`submission.py`** (`submit_ad`) | BLOCK 3 (no edit expected — Option A is call-site-free), BLOCK 5 (Q2 error boundary), BLOCK 6 (the "Ad not found" branch), BLOCK 8 (the promotion point) | **Four blocks, one function.** Serial order `3 → 5 → 6 → 8` is correct and a later block must re-read rather than assume. If Q2 chooses a retry boundary that touches `submit_ad`, BLOCK 5 lands before BLOCK 6's message change and before BLOCK 8's move. |
| **`immediate_alerts.py`, `alert_query.py`** | BLOCK 9 | Also named by phase 06's `PII-104` as **excluded** — if phase 06 does edit them, BLOCK 9 must re-read. Phase 01 owns the `send_alerts` idempotency. |
| **`copy_service.py`, `ad_copy.py`** | BLOCK 10 (single-draft policy, error boundary) | Phase 05's `AD-003` also edits `copy_ad`'s key reuse — disjoint region, but phase 05 must not ship before BLOCK 10 or it will re-derive the file. |
| **`ad_data/orm.py` + `ad_data/__init__.py`** | BLOCK 4 (`create_draft_ad`), BLOCK 6 (`touch_draft` heartbeat + its `__all__` re-export) | `apps.*` must **never** import `telegram_bot.*` — the heartbeat helper must live in `telegram_bot/services/ad_data/`, not in `apps/`. |
| **`ads/models.py`** | BLOCK 6 (`Ad.Meta.indexes` → `IX_ads_draft_sweep`), BLOCK 8/BLOCK 10 (reference only) | Also named by phase 05's `AD-002` and phase 15's authentication findings as excluded. One index entry, one migration. |
| **`locale/*/LC_MESSAGES/django.po`** | BLOCK 6, BLOCK 10 | Shared with phase 14. Append; never regenerate wholesale. `ru` and `bs` `msgstr` must both be non-empty. |
| **Migration numbers** | BLOCK 6 → `ads/0008_*`; BLOCK 9 → `search/0003_*` (Option B); BLOCK 8 → `media/0002_*` **only if** the DB schema changes | **Check the directory immediately before generating.** `core/0006_*` is claimed by phase 02 BLOCK 5 (Option A only) — **phase 03 needs no `core` migration**, and must not create one just to dodge the collision. |
| **`docs/02-database/db-retention.md`, `docs/02-database/db-indexes.md`** | BLOCK 5 (the "no lock timeout is configured" sentence), BLOCK 6 (retention table + `IX_ads_draft_sweep`) | Two blocks, two files, **disjoint regions** — but BLOCK 6 must re-read before editing. |
| **`.ai/audit/**`** | **Nobody.** Unmodifiable by mandate | 19 tracked deletions exist in the working tree. `git status --short .ai` must show no *new* modifications. |
| **`.ai/plans/**`** | Each Planner owns its own plan file only | This plan may not edit `01-…` or `02-…`. |

### 5.4 `03-VAL-003` — new, recorded here, routed **out** of phase 03's code

**Claim:** `AD-005` (phase 05, **HIGH**) and `03-DB-001` (this cycle, **MEDIUM**) describe
**the same defect** — `create_draft_ad`'s `except IntegrityError` recovery branch runs
queries against an already-aborted transaction because the `create` sits in the outermost
`atomic()` and no savepoint was ever created.

**Why it matters:** if both are reported at their filed severities, the final report
states a CRITICAL/HIGH pair for a defect that **destroys no data** — the rollback
*preserves* the pre-existing DRAFT row and no `pre_delete` deletion fires, so a sequential
retry succeeds. `create_draft_ad` is called from exactly **one** production site
(`telegram_bot/handlers/ad_create/entry.py::cmd_post`) inside a **single** bot process,
where concurrent calls serialise on the single asgiref `thread_sensitive` worker. The
trigger requires a second bot process.

**What phase 03 does:** ships **one** work item at **MEDIUM** (BLOCK 4). The correct
invariant to test is *"a draft is returned"*, not *"the seller's draft survived"* — the
report's original framing is wrong on that point and a test written against it would fail
against correct code.

**Routing:** **coordinator**, for the `AD-005` re-rating in phase 05. Phase 05 must not
ship a second patch (§5.2). BLOCK 4's gate is an acknowledgement, not an investigation, and
should not stall the phase if it never arrives.

### 5.5 `03-VAL-004` — new, recorded here, routed **out** of phase 03's code

**Claim:** two of the audit input's retained runtime reproductions do not survive contact
with the production code path. `V-04` observed that every record is wrapped in
`transaction.atomic()` — true only because **every call site was themselves inside a
transaction** at the time of measurement; the production autocommit path has no such
wrapper. `V-02` observed the analytics INSERT succeeding *inside* `handle_login_orm` — the
INSERT is in fact a statement Django issues **after** the savepoint block closes, so no
savepoint ever covered it.

**Consequence for this plan:** BLOCK 3's blast radius is **narrower** than the report
implies (§0.2 C-4: 9 call expressions across 6 modules, of which 3 are inside a caller
transaction). The narrower count makes the *reachability* argument **harder**, not easier
— which is why BLOCK 3 carries a Researcher and a mandatory runtime probe, and why the
ad-detail query budget (§0.2.3) is a first-class constraint rather than an afterthought.

**Routing:** **coordinator**, for the final report's evidence-quality note. No phase-03
block fixes an audit document. §0.2.4 lists every claim that was **not** re-derived, so the
report can be corrected once, centrally, rather than eleven times across blocks.

---

## 6. Out of scope for this plan

| Item | Reason |
|---|---|
| **`03-DB-006`** (rejected) | Rejected by the validator: the stated mechanism (`QuerySet.delete()` filtering on primary key only) does not hold for a non-fast-deletable model. The residue — a logged count that can disagree, and the redundant pre-delete scan — **is** `03-DB-011`, shipped in BLOCK 1. Re-examine only if the Django floor moves outside `>=5.2.16,<6.0`. |
| **`ENT-006` addendum elements** (the `migrate_locked` docstring and the "Requesting session advisory lock" log) | **Already shipped** by phase 01 in `7aac8d3`. DB-004 is the **timeout half only**. `test_migrate_locked.py::TestSessionLockLogging` is now a regression guard for it. |
| **`ENT-009`** | Absorbed by BLOCK 6 (`03-DB-003`). Filing it separately would produce two work items for one fix. |
| **`ENT-010` Half B** — `CONN_MAX_AGE` / connection lifecycle | **Rejected as intentional design** by phase 01 (PgBouncer async safety, zone C5). BLOCK 5 must not re-open it. `CONN_MAX_AGE = 0` comes from Django's global default, because `django-environ` 0.14.0's `db_url_config()` never emits it; `CONN_HEALTH_CHECKS` is set **nowhere** (§0.2 C-2). |
| **Making retention windows environment-configurable** | Directly contradicts `docs/02-database/db-retention.md`: *"All retention values are hardcoded… No environment variables or CLI arguments (beyond `--dry-run`) are read for retention durations."* BLOCK 6 keeps 30 minutes and changes the **predicate**, not the window. |
| **`AD-003`** (refcount on shared storage keys) | Phase 05. Different root cause from DB-005; BLOCK 8 must not add refcounting or remove `copy_ad`'s key reuse (§5.2). |
| **`PII-104`** (alert audience / consent) | Phase 06. BLOCK 9 owns delivery state, not recipient selection (§5.2). |
| **Raising the asgiref worker count** | Explicitly forbidden. `thread_sensitive` exists so a transaction and its connection stay on one thread; relaxing it breaks the single-dispatch-per-transaction guarantee. BLOCK 5's remedy is a bounded wait, not more workers. |
| **A bot watchdog timer for draft idle detection** | Phase 01 deliberately did not add one and provided the `probe` hook. BLOCK 6 uses a DB heartbeat — a different mechanism with a different failure mode. |
| **Redesigning the `advisory_lock` abstraction** | BLOCK 2 copies `try/finally`; BLOCK 7 may pass `session=True`. Neither introduces a new primitive, a new manager class, or a lock-ordering framework. The enum and the module are the contract. |
| **Speculative `AdvisoryLockId` allocation** | Phase 03 allocates **none** (§5.3). IDs 10 and 13–99 stay reserved. |
| **Rewriting `Ad.transition_to` / the state machine** | Referenced by BLOCK 6 and BLOCK 7 but not modified. `AD-002` (archive bypass) is phase 05. |
| **Changing `find_matching_ads` / the daily digest's matching semantics** | BLOCK 9 changes only the **delivery-state** contract. Matching semantics are the search feature's concern (phase 08). |
| **`_executor`, `Bot` lifecycle, `asyncio.run` per batch in `immediate_alerts`** | Existing, working, deliberate. Re-using a module-level `ThreadPoolExecutor` across loops is a hazard to raise as a **finding**, not to fix inside a MEDIUM DB finding. |
| **The `analytics_events` unique constraint / `ignore_conflicts`** | Phase 01's §5.3 boundary. The project deliberately allows duplicate analytics rows; BLOCK 3 does not add dedup. |
| **Consolidating the four `_run_in_subprocess` test helpers** | Phase 02 §6, phase 10/11. Phase 03 adds no subprocess helper and must not create a fifth copy. |
| **i18n framework changes, `makemessages` regeneration, locale-file rewrites** | BLOCK 6 and BLOCK 10 **append** strings. A wholesale regeneration would discard a concurrent phase-14 edit (§5.3). |
| **Any new dependency** | Nothing here needs one. Adding one would require `uv add`, a lockfile update, and a CI `uv lock --check` pass. |
| **The 19 uncommitted `.ai/audit/**` deletions** | Not this plan's to resolve. Recorded so no block's `git status` check mistakes them for its own work. |
| **The deleted `.ai/audit/03-db-concurrency/findings.md`** and its three sibling scripts | Tracked deletions. Recorded in §0.1 for traceability only; **not** an input, and no block may restore them. |
| **BLOCK 11's legacy sweep, if the coordinator de-scopes it** | A live de-scope option (§4.4), not a silent omission. The three production citations this cycle polluted must still be handled. |

---

## 7. Per-block risk register

Severity here is **this Planner's assessment of execution risk for the change**, not the
finding's severity. "Migration" covers DDL, backfill and rollback; "Lock ordering" covers
advisory-lock and row-lock acquisition order; "Transaction boundary" covers `atomic()`
nesting and savepoint depth; "Data migration" covers existing rows whose meaning changes.

| Block | Risk | Kind | Likelihood | Impact | Mitigation / detection | Residual |
|---|---|---|---|---|---|---|
| **All** | An implementor runs `git add -A` / `git commit -a` and commits the 19 `.ai/audit/**` deletions or another phase's uncommitted work, then the next phase's block clobbers it | Process | Med | **High** | §1's hard staging rule; `git status --short` immediately before **every** commit; the audit tree is unmodifiable by mandate; §5.2 names the specific files phase 03 must not clobber. | Very low |
| **All** | A block is executed with its `depends_on` incomplete, or two Implementors run at once | Process | Low | **High** | §4.1 serial order; one Implementor, strictly sequential. `3 → 5` is the edge that matters (a timeout plus an unfixed `record_event` makes DB-002 live). | Very low |
| **All** | A block's tests are **asserted** rather than **run**, or run on the host where there is no database | Process | Med | **High** | Every block names its exact Docker gate command; tests run **only** through the `test` service (§1). | Low |
| **All** | A gate's decision (Q1–Q12) is closed silently by the Implementor instead of by the Researcher/Planner | Process | Med | **High** | Every gated block states the gate in `extra_context` of its task YAML and requires the decision to be recorded in the commit message. §8.2 checks it. | Low |
| **All** | A new user-visible string ships without non-empty `ru` **and** `bs` translations | i18n | Med | Med | Only BLOCK 6 and BLOCK 10 add strings; both name the locale files and §5.3 forbids a wholesale regeneration that would clobber phase 14. | Low |
| **All** | A **shipped green test** that encodes a defect is "fixed" by changing production code instead | Correctness | Med | **High** | Project rule 2 is restated in §1. Six tests are explicitly slated for rewrite (BLOCK 2 ×2, BLOCK 3 ×2 under Option B, BLOCK 6 ×2, BLOCK 8 ×2, BLOCK 9 ×1, BLOCK 10 ×1) and **each block names the test and the justification**. §8.3 checks them. | Low |
| **1** | `AdImage` import left in a file that no longer uses it, or removed from one that does (`consent_hard_delete` uses a different field path) | Correctness | Med | Low | `uv run ruff check src/` catches F401; read before deleting. | Very low |
| **1** | The implementer "improves" `len(storage_keys)` into a live count query, reintroducing the very scan this block deletes | Correctness | Low | Med | The acceptance criteria forbid it explicitly. | Very low |
| **1** | A second deletion path is created, so `delete_photo` runs twice per key | Data | Low | **High** | `test_delete_photo_single_call.py` asserts exactly one call; `test_ad_image_delete_signal.py` pins the `pre_delete` → `on_commit` chain. Both must stay green. | Very low |
| **2** | `pg_advisory_unlock` is added to the transaction branch by copying the session branch too literally | Lock | Med | **High** | The binding constraint names the exact two lines to copy. An extra round-trip for **13** commands would be silent. | Low |
| **2** | The test rewrite keeps only the normal-exit assertion, reproducing the finding's blind spot | Observability | Med | Med | The rollback-path test is mandatory and must be **red against the pre-fix code**. | Low |
| **2** | The rewrite lands but the test file's module docstring still states *"on_commit fires only on successful commit — matching when `pg_advisory_xact_lock` releases"* | Documentation | Med | Med | The docstring is named in the task YAML's `semantic_anchors` and in the acceptance criteria. | Low |
| **3** | The **plain savepoint** variant ships: it looks like Option A, passes the existing suite, and does **not** fix the defect (the COMMIT still fails and the caller's business write is still lost) | Correctness | **Med** | **High** | The only control is a regression test that provokes a **real** server-side error. Binding constraint 5 forbids a mocked exception. | Low |
| **3** | The `SET CONSTRAINTS` subtlety is "simplified" away by a later reader because it is undocumented | Correctness | Med | **High** | The function docstring must state why the `SET` is mandatory. A reviewer should treat its absence as a defect. | Med — accepted |
| **3** | `SET CONSTRAINTS` fails at runtime because a **generated** FK constraint name was copied from the report rather than read from the live schema | Correctness | Med | **High** | Q3's note: names **must** be read from the Docker test database. A wrong name raises `OperationalError` — which `record_event` would then swallow, silently. | Low |
| **3** | Option 2's `on_commit` is placed inside a **nested** atomic, so it fires at *savepoint* release rather than at the outer commit — silently reproducing the defect | Correctness | Med | **High** | Each edited call site must be checked against the enclosing `atomic()` nesting depth; the option table states this explicitly. | Low |
| **3** | The ad-detail render budget (`_QUERY_BOUND = 16`) is silently exceeded by the added transaction-control statements | Regression | **Med** | Med | §0.2.3; binding constraint 1; the Implementor measures and either derives a new bound or records why the count did not change. | Low |
| **4** | A test is written against the report's wrong *"the seller's ad is destroyed"* claim and fails against correct code | Correctness | Med | Med | The binding invariant is *"a draft is returned"*. Stated in the block and in §8.3. | Very low |
| **4** | The in-repo precedent (`login.py`) is stale — phase 01's `ENT-005` extraction moved it — and the fix copies the wrong shape | Correctness | Med | Med | The Auditor re-locates the precedent **by symbol**; §0.2 C-5 records the stale citation. | Low |
| **4** | The cleanup `Ad.objects.filter(...).delete()` now runs inside the outer transaction and could itself be rolled back by a later failure | Transaction | Low | Med | That is **correct** behaviour (one unit of work), but it must be understood. Stated in the block's risk section. | Low |
| **5** | A global timeout below ~1 s turns six shipped concurrency tests red, and the implementer "fixes" the tests instead of the value | Regression | **Med** | **High** | Q1's table lists all six. The value must be chosen so those tests keep asserting what they mean, or their intent must be preserved under a **recorded** change. | Low |
| **5** | A new `OperationalError` path in a web view surfaces as an uncaught 500, or in a bot handler as an unhandled exception | Regression | Med | **High** | Q2's inventory exists precisely to prevent this; it is a hard pre-implementation step. | Low |
| **5** | `base.py` is edited on a stale read and phase 02's `ALLOWED_ENV_VARS` regrouping or a guard is clobbered | Process | Med | Med | §1 staging rule; §5.3 names `base.py` as the most contended file after `conftest.py`; re-read immediately before editing. | Low |
| **5** | `pg_advisory_xact_lock` waits are bounded but the **scheduler's** own `asgiref` dispatch is not, so a bounded error still surfaces as a `CommandError` | Regression | Med | Med | Scheduler `post_migrate`/`load_catalog`/`seed` paths and the hourly `send_alerts` sweep must be in the Q2 inventory. | Low |
| **5** | The new `OPTIONS` key is added only to the `DATABASE_URL` branch, leaving the discrete branch unparsable | Correctness | Med | Low | The branch is **dead in deployment** but still parsed; both must carry the key. | Very low |
| **6** | The predicate flips to `updated_at` while the heartbeat is incomplete ⇒ live drafts are reaped (the original defect, inverted) | **Data loss** | Med | **High** | Mandatory internal order `(a)→(b)→(c)→(d)`; the back-dated-`updated_at` survival test is the direct guard. | Low |
| **6** | `IX_ads_draft_sweep` is not changed with the predicate ⇒ the hottest sweep degrades to a sequential scan | Performance | Low | Med | The migration is a named deliverable and `docs/02-database/db-indexes.md` is one of the three DOC-UPDATEs. | Low |
| **6** | The heartbeat is missed at a step (a future handler that mutates an ad input without calling it) | Correctness | Med | Med | Q5's Option A weakness stated explicitly; Option B removes the class. §8.3 requires the FSM inventory to be recorded. | Low |
| **6** | The heartbeat adds ~10 UPDATEs per dialog to the single asgiref worker thread — the same queue BLOCK 5 is about to bound | Performance | Med | Med | The write must be a single-column `UPDATE`, not a full `save()`, and must not open a transaction beyond the statement. | Low |
| **6** | `create_test_ad()` in `conftest.py` is edited to support the new tests, colliding with every other phase | Process | **Med** | **High** | BLOCK 6 must not touch `conftest.py` (§5.3). Back-dating is done locally in the two test files. | Low |
| **7** | Q11 is resolved wrongly ⇒ batching ships but **mutual exclusion is silently lost** between two concurrent sweeps | Lock | **Med** | **High** | The "advisory lock acquired **exactly once** and held across all batches" test is the only control, and it is written to be independent of `session=True\|False`. | Low |
| **7** | `order_by("pk")` is lost during per-batch re-derivation, introducing a deadlock against a concurrent `ad_edit` | **Lock ordering** | Med | **High** | Binding invariant 3; a real-concurrency deadlock test is required. | Low |
| **7** | `test_sweep_lock_structure.py`'s `session is False` assertion is relaxed for **all 13** commands instead of the two affected ones | Regression | Med | Med | The acceptance criteria constrain the amendment to the two named entries; the other 11 must be unchanged. | Low |
| **7** | The failure test is written as *"everything rolls back"*, which passes against the **pre-fix** code and proves nothing | Testing | **Med** | Med | The test must assert the **opposite** — batches 1..N-1 **are** committed — and be demonstrated red first. | Low |
| **8** | `TestSubmitAdStagingMove` is rewritten but its **class docstring** still calls the promote-before-transaction ordering *intended*, so the next reader reverts the fix | Documentation | **Med** | **High** | The docstring is a named deliverable in both the file surface and the task YAML's `semantic_anchors`. | Low |
| **8** | Option A creates a sweep-excluded subdirectory that nothing reclaims ⇒ data loss traded for unbounded growth | Storage | Med | Med | The reclamation test is mandatory. Without it Option A is not shippable. | Low |
| **8** | Option A changes what `AdImage.save()`'s SHA-256 sees (file still in the staging subdirectory vs promoted), silently corrupting content dedup | **Data** | Med | **High** | Note 6; a dedicated pre/post-promotion hash test is required. | Low |
| **8** | The alternative "lock the submit path" remedy is chosen, serialising every seller submission against an `os.walk` | Availability | Low | **High** | Stated as the strongest argument against it; the Researcher must confront it before choosing Option B. | Very low |
| **8** | A rollback of a deployed Option A leaves files that the rolled-back code then treats as orphans | Data | Low | **High** | The rollback plan must include a one-off reclamation of the new directory. Stated in the block. | Low |
| **8** | `AD-003`'s refcounting is merged in "while we are here" | Scope | Med | Med | Explicitly forbidden (§5.2); BLOCK 8 must not change `delete_adimage_files_on_delete`. | Low |
| **9** | Option A alone is shipped and the feature is recorded as fixed | Correctness | **Med** | Med | The commit message must state the concurrency path is unproven and that Option B remains required. §8.3 checks it. | Low |
| **9** | Option B's flag is written **after** the send ⇒ a crash duplicates the message | Correctness | Med | Med | Binding constraint: the flag is written **before** dispatch, in the same transaction as the row. | Low |
| **9** | A `NOT NULL DEFAULT false` backfill re-notifies every previously immediate-sent pair — a **mass duplicate send** on first enable | Data | **Low** | **High** | The column must be **nullable with no backfill**; a dedicated backfill test is required. | Low |
| **9** | Phase 01's `send_alerts` idempotency work (`fbbb6cf`) is reverted by an over-broad "simplification" | Regression | Low | **High** | §5.1 names it; its tests must stay green. | Very low |
| **9** | The migration number `search/0003_*` collides with a concurrent phase | Process | Low | Med | Check the directory immediately before generating (§5.3). | Low |
| **10** | Option C is shipped by default ("just improve the message"), leaving the missing policy unaddressed | Correctness | Med | Med | Option C is explicitly **forbidden**; if no decision arrives, default to A and record that it was a default, not a decision. | Low |
| **10** | The raw psycopg `IntegrityError` text (constraint name, `DETAIL Key …`, `CONTEXT INSERT INTO`) keeps reaching Telegram users | Data exposure | Low | Med | A test asserts the message contains no raw driver text. | Very low |
| **10** | Option A deletes the seller's in-progress draft before the copy commits ⇒ a later failure loses both | **Data loss** | Low | **High** | Delete and create in one transaction; file deletions after commit. | Low |
| **11** | A comment rewrite in a file **another phase is editing right now** causes a merge conflict or a clobbered edit | Process | **Med** | Med | §5.2 + §5.3 name the contended files; re-read before editing; stage explicit paths. | Low |
| **11** | A cycle number is **inferred** rather than evidenced, producing a confident-but-wrong attribution — arguably worse than today's honest ambiguity | Documentation | Med | Med | Note 4: prefer the descriptive form (Option C) wherever attribution is uncertain. Never infer. | Low |
| **11** | An implementer renames tests or touches assertions "while in there" | Scope | Low | Med | **Assertions are immutable** — stated in the block and in the task YAML's `extra_context`. | Very low |
| **11** | The block is treated as cosmetic and de-scoped entirely, leaving three production citations ambiguous | Process | Med | Med | The three are non-negotiable under **any** option (§3.11.1 note 2). | Low |

---

## 8. Definition of done for the whole plan

Phase 03 is complete when **all** of the following hold.

### 8.1 Scope

- [ ] All 11 `03-DB-*` findings have a recorded disposition: **10 implemented**
      (`03-DB-001`, `002`, `003`, `004` *timeout half only*, `005`, `007`, `008`, `009`,
      `010`, `011`), **1 rejected** (`03-DB-006`, with the residue shown to be covered by
      `03-DB-011`).
- [ ] `03-DB-004`'s commit message states explicitly that the `ENT-006` addendum was
      already shipped by phase 01 in `7aac8d3` and that only the timeout half landed here.
- [ ] All 4 `03-VAL-*` findings have a recorded disposition:
      `VAL-001` tracker half **decided** (§5.2) and source half **shipped or explicitly
      de-scoped** (§4.4); `VAL-002` landed as the `3 → 5` ordering edge and was honoured;
      `VAL-003` escalated to the coordinator (§5.4) with BLOCK 4 shipping the single work
      item; `VAL-004` routed to the coordinator's final report (§5.5).
- [ ] Every gated block (**3, 5, 6, 7, 8, 9, 10**) has a **written** decision for its open
      question, naming the option chosen and the consequences accepted. Silence is not an
      acceptable outcome.
- [ ] `03-DB-006`'s rejection is restated in the final report so it is not silently
      re-filed by a later phase.

### 8.2 Gates — all green

- [ ] `uv run ruff check src/` → exit 0.
- [ ] `uv run basedpyright src/` → **0 errors**.
- [ ] `.\Makefile.ps1 test` → full suite green (seed marker skipped).
- [ ] `.\Makefile.ps1 test-recreate` executed at least **once after BLOCK 6's migration**
      and at least **once after BLOCK 9's migration** if `search/0003_*` was generated.
- [ ] `git status --short .ai` shows **no new modifications** beyond the 19 pre-existing
      `.ai/audit/**` deletions. No audit-phase file was edited, restored or re-created.
- [ ] Every block's exact gate command from §3 was run and green, **not** the full suite
      alone.
- [ ] ID-sweep: zero remaining ambiguous `DB-0\d\d` citations among the files BLOCK 11 was
      scoped to cover — **or** a recorded de-scope with the three non-negotiable
      production citations handled.
- [ ] BLOCK 3's runtime probe was executed against the Docker test database **before**
      the fix was written, its result recorded, and the probe deleted (not committed).
- [ ] No commit was made without an explicit user request; no `git reset`, `git checkout`
      or `git stash` was run at any point.

### 8.3 Per-finding behavioural confirmation

- [ ] **`03-DB-001`** — with `uq_ads_single_draft_per_user` forced to fire,
      `create_draft_ad` **returns a draft** rather than propagating an `InternalError`.
      The existing `TestCreateDraftAdCrashRecovery` cases (rollback preserves the row,
      `delete_photo` not called on rollback) pass unchanged.
- [ ] **`03-DB-002`** — inside a caller-owned `atomic()`, a **real server-side** database
      error in `record_event` leaves the caller's business write **committed**. The new
      test was demonstrated **red** against the pre-fix code. `submit_ad`'s
      roll-back-on-moderation-failure case passes unchanged. The ad-detail query budget
      was **measured**: either `_QUERY_BOUND` was raised with a stated derivation, or the
      commit message records why the count did not change.
- [ ] **`03-DB-003`** — a draft with an old `created_at` and a **recent** `updated_at`
      **survives** the sweep; a draft with an old `updated_at` **is deleted**; a heartbeat
      write on a dialog step keeps the draft alive. `IX_ads_draft_sweep` is on
      `(status, updated_at)`. An expired draft produces the **translated**,
      seller-recoverable message, not the generic moderation-failure text.
- [ ] **`03-DB-004`** — a call holding a row lock ~1 s is **not** blocked indefinitely: the
      wait is bounded and observable. All six shipped ~1 s concurrency tests still assert
      what they mean. `record_event` handles the resulting `OperationalError`. No global
      worker-count change was made.
- [ ] **`03-DB-005`** — a `sweep_orphaned_media` run overlapping a `submit_ad` never
      deletes a file whose `AdImage` row commits, **and** files orphaned by a rolled-back
      submit are reclaimed within a bounded time. `AdImage.save()`'s content hash is
      identical before and after any promotion move.
- [ ] **`03-DB-007`** — a failed `_run_send` followed by a `send_alerts` run **still
      delivers**. An already-delivered pair is **not** delivered twice. A pair delivered
      only by the daily path is still excluded by the immediate matcher. Pre-existing rows
      are `NULL` and are not filtered out. The feature still does nothing with
      `IMMEDIATE_ALERTS_ENABLED=False`.
- [ ] **`03-DB-008`** — a failure in batch *N* leaves batches 1..*N*-1 **committed**. The
      advisory lock is acquired **exactly once** and held across all batches. The queryset
      is re-derived per batch. `order_by("pk")` lock ordering is preserved (and **added**,
      where missing, for `recompute_normalized_prices`). The test was demonstrated **red**
      against the pre-fix code.
- [ ] **`03-DB-009`** — a seller with an existing `DRAFT` running `/copy` ends with the
      chosen option's outcome, and the same policy is demonstrably in force in **both**
      `create_draft_ad` and `copy_ad`. The failure message contains **no** raw driver text.
      `test_ad_copy.py`'s `"failed"` assertion passes unchanged.
- [ ] **`03-DB-010`** — the release line is emitted on the **rollback** path as well as the
      normal path, the exception still propagates to the caller, and `pg_advisory_xact_lock`
      is issued exactly once with no `pg_advisory_unlock` added to the transaction branch.
      Both rewritten tests were demonstrated **red** against the pre-fix code.
- [ ] **`03-DB-011`** — no `storage_keys` reference remains in the six commands;
      `delete_photo` still runs **exactly once** per key; `consent_hard_delete` still logs
      its user count.
- [ ] **`03-VAL-001`** — `advisory_lock.py` no longer contains two different
      `DB-010` references three lines apart, and this cycle's own citations are
      cycle-scoped.

### 8.4 Cross-phase integrity

- [ ] Phase 01's `test_migrate_locked.py::TestSessionLockLogging` passes **unchanged**.
- [ ] Phase 01's `send_alerts` idempotency behaviour (`fbbb6cf`) is intact.
- [ ] Phase 01's `ENT-009` is recorded as **absorbed** by `03-DB-003`, not re-shipped.
- [ ] `src/backend/conftest.py` is **unmodified**.
- [ ] `AdvisoryLockId` gained **no new member**, or — if a design forced one — `enums.py`,
      the lock-allocation table in `advisory_lock.py`'s docstring, and
      `test_advisory_lock_ids.py` all changed in the same commit and the coordinator was
      notified.
- [ ] No `apps/*` module imports `telegram_bot/*` (the heartbeat helper lives in
      `telegram_bot/services/ad_data/`).
- [ ] `copy_ad`'s storage-key reuse and `delete_adimage_files_on_delete` are unchanged
      (`AD-003`, phase 05, untouched).
- [ ] Recipient-selection logic in `find_matching_saved_searches` is unchanged beyond the
      delivery-state filter (`PII-104`, phase 06, untouched).
- [ ] `CONN_MAX_AGE` / connection lifecycle is unchanged (`ENT-010` Half B stays rejected).
- [ ] Migration numbers were checked against their directories **immediately before**
      generation; `apps/core/migrations/` gained nothing in this phase.
- [ ] `docs/02-database/db-retention.md` no longer claims *"no lock timeout is
      configured"*, and `docs/02-database/db-indexes.md` matches `IX_ads_draft_sweep`.
- [ ] Locale files were **appended** to, never regenerated wholesale.
- [ ] No new dependency was added (`uv.lock` unchanged).

### 8.5 Project conventions

- [ ] Every new constant is a named module-level constant or a `StrEnum`/`IntEnum` member,
      never an inline literal or a dict-of-strings (project rule 10).
- [ ] No `print()`; `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
- [ ] All comments, docstrings, log messages and error messages are in **English**.
- [ ] Every `with transaction.atomic():` line carries the project's established
      `# pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed;
      Atomic.__enter__/__exit__ untyped` suppression (or a typed equivalent — never a
      bare suppression).
- [ ] Business logic lives in `services/`; no new logic was added to a view or a handler
      beyond the thin boundary change its block requires.
- [ ] Every non-trivial behaviour change has a test that verifies **logic and component
      interaction** — not a variable's absence, not a log string, not a line count. (This
      is why BLOCK 1 and BLOCK 11 add **no** tests.)
- [ ] Filesystem side effects happen only **after** commit, via `transaction.on_commit()`.
- [ ] No task target is a line number; every target is a file plus a semantic symbol.
- [ ] `pytestmark` conventions follow the surrounding file.
- [ ] `uv run ruff check --fix src/` was run if imports were reordered (`ruff format` is
      not the project convention).
- [ ] New test code is bandit-clean (list-form `subprocess.run([sys.executable, ...])`,
      no literal `/tmp`) so a future `VAL-006` fix does not redden the `security` job.

### 8.6 Deliverables

- [ ] The `03-VAL-003` re-rating request for phase 05's `AD-005` is recorded and
      communicated to the coordinator — **not** silently decided.
- [ ] The `03-VAL-004` evidence-quality note (§0.2.4) is recorded for the final report,
      including every runtime claim that was **not** re-derived.
- [ ] The `03-VAL-001` convention (`NN-<PREFIX>-00N`, §5.2 items 1–4) is recorded in this
      plan and handed to the phases 04–15 coordinators, so twelve plans do not invent
      twelve conventions.
- [ ] `docs/02-database/db-retention.md`'s lock-wait semantics match the shipped behaviour.
- [ ] This plan file is updated to mark each block's completion, so the phase coordinator
      has a single status surface.
- [ ] No commit was made without an explicit user request.