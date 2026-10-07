---
plan_id: "17-ad-lifecycle-execution"
title: "Execution Plan — Phase 05 (Ad Lifecycle, Categories & Moderation)"
slug: "17-ad-lifecycle-execution"
phase: "05"
source_plan: ".ai/plans/05-ad-lifecycle-remediation.md"
source_report: ".ai/audit/99-validation/05-ad-lifecycle-validated-findings.md"
code_context: ".ai/tmp/code-context-phase05-74848c6.md"
anchor_commit: "74848c6"
source_plan_anchor: "aa2a6b0"
verified_head_at_write: "f56c401"
date: "2026-10-02"
status: "in_progress"
blocks: 14
language: "en"
owner_gates_open: ["Q1", "Q2", "Q4", "Q5", "Q6", "Q7", "Q8-value", "Q10-value"]
gates_closed_in_source_plan: ["Q3", "Q8-mechanism", "Q9-sizing", "Q11", "Q12"]
modifies_audit_tree: false
modifies_other_plans: false
---

# Execution Plan — Phase 05 · Ad Lifecycle, Categories & Moderation

This document is the **single status surface** for phase 05 and the brief every Implementor
receives. It decomposes `.ai/plans/05-ad-lifecycle-remediation.md` (the **source plan**) into
executable blocks.

**Authority order.** The Auditor's `{code_context}` at `.ai/tmp/code-context-phase05-74848c6.md`
is **authoritative over the source plan**. Where this document and the source plan disagree,
this document is right and §1 says why. The validated source report is reference only.

**Drift.** The source plan is anchored at `aa2a6b0`, **40 commits stale**. The code context
was measured at `74848c6`. This document was written against **`f56c401`**, one commit past
the code context (`f56c401 docs(auth): close the phase-04 record gaps on AUT-003 and VAL-002`).
That commit touches **no phase-05 file surface** (`docs/99-agent/architecture.md`,
`apps/core/management/commands/create_admin_user.py`, `apps/core/tests/test_login_issue_template.py`,
`apps/users/services/login_token.py`, `apps/users/tests/test_consent.py`,
`apps/users/tests/test_login.py`, `apps/users/views/consent.py`). The facts below are therefore
valid at both anchors. Every block must still re-read its own file surface before editing.

**Working tree is dirty by design.** 19 tracked `.ai/audit/**` deletions, 6 modified
`.ai/plans/*`, untracked `.ai/tmp/`, `staticfiles/`, `.ai/plans/16-…`.
**`.ai/audit/**` is unmodifiable by mandate.** No `git add -A` / `git add .` / `git reset` /
`git checkout` / `git stash` / `git clean` at any point. Stage explicit paths; re-read
`git status --short` immediately before every commit.

**Baseline at write time (re-verified):** `uv run ruff check src/` → `All checks passed!`.
`uv run basedpyright src/` → **0 errors, 0 warnings, 0 notes**. Test DB
`mko-bazuna-test-db-1` up on host port `5433`.

> The source report's *"12 basedpyright errors in 2 files"* is **superseded and re-measured at 0**.
> It must not appear in any block, task YAML, commit message, or final report. The scope fix is
> `8bf0517 ci(scope): cover telegram_bot in lint and typecheck gates`.

---

## §0.1 Finding status at HEAD and disposition

Status vocabulary is taken verbatim from the code context §2. Disposition is this execution's
ruling and is binding on the Implementor.

| Finding | HEAD status (code context §2) | Shipped by | Disposition in this execution | Block | Readiness |
|---|---|---|---|---|---|
| `AD-001` admin form bypasses the state machine | **OPEN** | — | **DEGRADED.** Four unconditional violations ship; the `status`-read-only half waits on Q1 | BLOCK 6 | OWNER-GATED → DEGRADED |
| `AD-002` editing a failed ad is a dead end | **OPEN** | — | **OWNER-GATED.** Degradable: the allow-list conversion is separable from the Q5 rule | BLOCK 8 | OWNER-GATED → DEGRADED |
| `AD-003` `copy_ad` aliases photo files | **MOOT / RETIRED** | `64a9de6` | **SUPERSEDED.** Retirement is now evidenced in the tree, not only by phase 07's ruling | BLOCK 14 | RECORD-ONLY |
| `AD-004` manual archive deleted 60 d after the click | **OPEN** | — | **OWNER-GATED.** Cannot be partially delivered; "correct" is undefined without Q4 | BLOCK 7 | OWNER-GATED |
| `AD-005` `create_draft_ad` race backstop dead | **ALREADY FIXED** | `664b572` | **SUPERSEDED.** Source plan's "still open in the tree" is **FALSE**. Ship nothing | BLOCK 14 | MOOT-SUPERSEDED |
| `AD-006` seller-scoped dedup returns another ad's row | **OPEN** | — | **OWNER-GATED.** Q6 is genuinely live: `MEDIA-002` has **not** been executed | BLOCK 13 | OWNER-GATED |
| `AD-007` draft sweep uses `created_at` | **MOOT** | `2697796` (+6) | **SUPERSEDED.** Sweep filters `updated_at__lt`; the message shipped too | BLOCK 14 | MOOT-SUPERSEDED |
| `AD-008` `ON_MODERATION` never durable | **OPEN** | — | **OWNER-GATED.** Exactly 2 production writers confirmed | BLOCK 5 | OWNER-GATED |
| `AD-009` price edit does not restart the clock | **OPEN** | — | **SHIP.** Q3 closed as Option B′ | BLOCK 2 | READY-WITH-CORRECTIONS |
| `AD-010` bulk JSON API: no tx, no lock, errors swallowed | **OPEN (narrow)** | — | **SHIP.** Q11 closed as per-ad `atomic()` + `select_for_update()` | BLOCK 9 | READY-WITH-CORRECTIONS |
| `AD-011` `archived_at` not cleared on reactivation | **OPEN** | — | **SHIP** with BLOCK 1 | BLOCK 1 | READY-WITH-CORRECTIONS |
| `AD-012` `ad_copy` leaks raw driver error | **ALREADY FIXED (both halves)** | `ba1b059` | **SUPERSEDED.** BLOCK 11 as written is a **duplicate-patch hazard** (R-3, R-17) | BLOCK 11 | MOOT-SUPERSEDED |
| `AD-013` transition matrix is method-local | **OPEN** | — | **SHIP** with BLOCK 1 | BLOCK 1 | READY-WITH-CORRECTIONS |
| `AD-014` `AdImage.position` unconstrained | **OPEN** | — | **SHIP.** Q9-sizing closed; the one query is BLOCK 10's pre-flight | BLOCK 10 | READY-WITH-CORRECTIONS |
| `AD-015` `ads_auto_publish=False` does not hide ads | **PARTIALLY FIXED** | `a19a0ee` (`UserAdmin` half) | **RECORDED, not fixed.** The record must say the `UserAdmin` half is **already shipped** (R-21), not "deferred" | BLOCK 14 | RECORD-ONLY |
| `AD-016` expired draft reported as moderation failure | **PARTIALLY FIXED** | `0a90650` (bot message half) | **SHIP the narrowed residual.** The message exists; `submit_ad`'s contract and `state.clear()` do not | BLOCK 12 | READY-WITH-CORRECTIONS |
| `VAL-001` bare audit IDs collide across cycles | **PARTIALLY FIXED** | `fd8c423` | **NARROWED.** Deliverable is **two** bare IDs, not three (R-7) | BLOCK 1 + BLOCK 14 | READY-WITH-CORRECTIONS |
| `VAL-002` suite fabricates `ON_MODERATION` | **OPEN** | — | **SHIP.** Premise survives; shape and size change materially (C-3, C-22) | BLOCK 4 | READY-WITH-CORRECTIONS |
| `VAL-003` human approval path is dead code | **OPEN** | — | **SHIP.** The widen-narrow asymmetry the fix depends on is fully intact | BLOCK 3 | READY |
| `VAL-004` storage-key ownership decision | **MOOT — resolved and shipped** | `64a9de6` | **RESOLVED.** Reinforce the record with the commit; fix `db-retention.md:155` | BLOCK 14 | RECORD-ONLY |
| `VAL-005` one decision, three hats | **OPEN (all three docs still disagree)** | — | **OWNER-GATED** via Q4; a fifth, executable conflict is now known | BLOCK 7 + BLOCK 14 | OWNER-GATED |
| `VAL-006` no single lifecycle-write owner | **OPEN** | — | **OWNER-GATED** via Q1; BLOCK 6's degradable half still ships | BLOCK 6 | OWNER-GATED → DEGRADED |

**Tally at the anchor:** 0 rejected · 1 retired (`AD-003`) · 2 already fixed (`AD-005`,
`AD-012`) · 2 moot (`AD-007`, `VAL-004`) · 3 partially fixed (`AD-015`, `AD-016`, `VAL-001`) ·
14 fully open. **Live open `AD-*` items: 11** (`001, 002, 004, 006, 008, 009, 010, 011, 013,
014` = 10, plus `AD-015`'s behaviour half), because `AD-012` and `AD-016` are partial. The
source plan's `§0.4` severity table and `§8.1` disposition counts must be re-derived from this
table, not from the source plan's tally.

### §0.2 Blocks at a glance

| Block | Findings owned | Readiness (code context §9) |
|---|---|---|
| BLOCK 1 | `AD-013`, `AD-011`, `VAL-001` (part) | READY-WITH-CORRECTIONS |
| BLOCK 2 | `AD-009` | READY-WITH-CORRECTIONS |
| BLOCK 3 | `VAL-003` | **READY** |
| BLOCK 4 | `VAL-002` | READY-WITH-CORRECTIONS |
| BLOCK 5 | `AD-008` | BLOCKED-ON-OWNER-GATE (Q2) |
| BLOCK 6 | `AD-001` (+ `VAL-006` via Q1) | BLOCKED-ON-OWNER-GATE (Q1) — **DEGRADED** |
| BLOCK 7 | `AD-004`, `VAL-005` | BLOCKED-ON-OWNER-GATE (Q4) — undisclosed scope multiplier |
| BLOCK 8 | `AD-002` | BLOCKED-ON-OWNER-GATE (Q5) |
| BLOCK 9 | `AD-010` | READY-WITH-CORRECTIONS |
| BLOCK 10 | `AD-014` | READY-WITH-CORRECTIONS |
| BLOCK 11 | `AD-012` (bot half) | **MOOT — MUST BE RE-SCOPED** |
| BLOCK 12 | `AD-016` | READY-WITH-CORRECTIONS |
| BLOCK 13 | `AD-006` | BLOCKED-ON-OWNER-GATE (Q6) — **live, not pre-empted** |
| BLOCK 14 | records: `AD-003`, `AD-005`, `AD-007`, `AD-012`, `AD-015`, `VAL-004`, `VAL-005`/`VAL-006` answers, `VAL-001` boundary | READY-WITH-CORRECTIONS |

---

## §1. Corrections this execution absorbs

**Read this section first. It overrides the source plan.** Every Implementor briefs from this
document and not from `.ai/plans/05-ad-lifecycle-remediation.md`.

### C-3 / VAL-002 census — the numbers are these, not the source plan's

The source plan carries three mutually inconsistent figures ("34", "~62", "~62/93"). The
authoritative census at the anchor is:

| Channel | Count | Breakdown |
|---|---|---|
| **Channel A — call sites that OMIT `status=`** (the silent channel) | **63 sites in 7 files** | **62 backend** (6 files) + **1 bot** (`src/telegram_bot/tests/test_ad_lifecycle.py`) |
| **Channel B — explicit `status=AdStatus.ON_MODERATION)`** | **40 occurrences** | **2 production** (`get_pending_queue_size`, `bulk_approve`) + **1 cleanup** (`test_moderation_analytics.py`) + **37 test fabrication** across 8 files |
| **Channel C — `transition_to(AdStatus.ON_MODERATION)`** | **12 occurrences** | **2 production** (`submit_ad`, `ad_reactivate`) + **9 test** across 4 files + 1 prefix near-miss (`moderation_log.py` targets `ON_MODERATION_FAILED` — **not** a writer) |
| Channel D — negative checks | **0** | no `status="on_moderation"` string form, no dynamic `AdStatus(...)` form, no third ad-factory helper |

**560 of 622 backend call sites already pass `status=` explicitly** (81.0 %). **51 of the 63
omissions (81 %) are concentrated in two files**: `test_priority_service.py` (27) and
`test_priority.py` (24).

Channel B is **nearly disjoint** from Channel A — only `test_moderation_views.py` appears in
both (1 omission, 16 explicit). `test_db_lock_timeout.py` (Channel A) and
`test_db_lock_timeout_boundary.py` (Channel B) are **different files**.

**The ninth taxonomy class.** The source plan's taxonomy is (a) consumer / (b) producer /
(c) incidental / (d)…). It does **not** name the class the 9 Channel-C test sites belong to:
**matrix-valid but transaction-boundary-bypassing** — they reach `ON_MODERATION` through the
*real* matrix edge from `DRAFT`/`ARCHIVED`, and in a test they commit. Any triage in BLOCK 4
must classify these nine separately. A three-class taxonomy does not cover them.

**Consequence for BLOCK 4's plan text.** The "~3× larger than stated" claim was correct in
*direction* and wrong in *arithmetic*. The census number is **precise today**; what will drift
is the **classification**, not the count. The source plan's estimate that "roughly half of
these fabricated tests would stay green" is a statement about `AD-008`'s remediation, not about
the census, and remains the right risk.

### C-22 — BLOCK 4's "both conftests must change together" is VOID

`create_test_ad` and `create_test_ads_bulk` are defined in **exactly one place**:
`src/backend/conftest.py`. `src/telegram_bot/tests/conftest.py` does **not** redefine them; its
own module docstring states that `create_test_ad` "IS shared: it is imported from the backend
conftest via `from conftest import create_test_ad` (resolved through `pythonpath`)". The
mechanism is `pyproject.toml`'s `pythonpath = ["src", "src/backend"]` — the same import appears
in `src/backend/apps/core/tests/test_sweep_delete.py`.

There is a **third** conftest, `src/backend/apps/ads/tests/conftest.py`, which redefines only
lookup fixtures (`purpose_lookup`, `feature_lookup`, `condition_lookup`) and **no ad factory**.

**Consequence.** Changing the default in `src/backend/conftest.py` changes it for both packages
**atomically**. The source plan's two-file hard requirement collapses to a single-file edit, and
its justification ("a shared helper means a single point of change") is **wrong in the other
direction**: a shared helper means a single point of change, which is a **benefit**.
Implementing BLOCK 4 as written would create an unnecessary modification to
`src/telegram_bot/tests/conftest.py` and could tempt an Implementor to add a guard that
`pythonpath` already provides (R-2). **Do not edit the bot conftest.**

### Already shipped — six items BLOCK 11 and BLOCK 14 as written would re-ship

| Finding / half | Shipped by | Evidence | Consequence |
|---|---|---|---|
| `AD-005` — `create_draft_ad` savepoint | **`664b572`** | `src/telegram_bot/services/ad_data/orm.py` (+8/−1), `src/telegram_bot/tests/test_create_draft_ad.py` (+45) | Ship **nothing**. The source plan's "still open in the tree" is **FALSE** |
| `AD-007` — draft sweep predicate | **`2697796`** (+ `8ddfebc`, `aa9038e`, `a0d9dca`, `2361cb0`, `feb9cb0`, `f45a755`, `0a90650`) | `sweep_drafts.Command.handle` filters `updated_at__lt`; migrations `0006_ad_ix_ads_draft_sweep` + `0008_remove_ad_ix_ads_draft_sweep_ad_ix_ads_draft_sweep` | Moot, **including** the seller-facing message |
| `AD-012` — bot half | **`ba1b059`** | `src/telegram_bot/handlers/ad_copy.py` renders `_("Failed to copy ad.")`; `logger.exception(...)` retained; msgid present in `ru` (non-empty), `bs`, `en`; `test_copy_unexpected_error_hides_driver_text` shipped | **BLOCK 11's CWE-209 core is already shipped** |
| `AD-012` — DB half | **`ba1b059`** | `copy_ad` deletes the seller's `DRAFT`, wraps the create in a savepoint with `try` outside, `except IntegrityError:` cleanup-and-retry once | Ship **nothing** |
| `AD-003` — `pre_delete` refcount | **`64a9de6`** | `delete_adimage_files_on_delete` computes `shared = set(AdImage.objects.filter(image__in=keys).exclude(pk=instance.pk).values_list("image", flat=True))` and deletes only `orphaned`; docstring warns *"Do not 'simplify' the exclusion away."* | **RETIRED**, and the retirement is now **evidenced in the tree**. Mechanism is an **existence check at delete time, not a stored refcount** |
| `AD-015` — `UserAdmin` half | **`a19a0ee`** | `apps/users/admin.py` now has `form`, `add_form`, `fieldsets`, `add_fieldsets`, `readonly_fields` (incl. `ads_auto_publish`), `get_form`, `get_fieldsets`, `get_readonly_fields` | The record must say **shipped**, not "deferred" (R-21) |
| `AD-016` — bot message half | **`0a90650`** | `process_preview` probes `_get_ad_status(...) is None` and renders `_("Your draft expired and was deleted. Please start again with /post.")`; in `ru` (non-empty), `bs`, `en` | BLOCK 12 must **reuse, never re-author**, this string |

**BLOCK 11 is a duplicate-patch hazard (R-3, R-17).** See §3 BLOCK 11 for the re-scope.

### C-15 — a new `conftest.py` contention the source plan does not record

Under **Q4 options (i) or (ii)**, the whole of
`src/backend/apps/core/tests/test_sweep_delete.py` goes red — `TestDeleteSweep` (6 methods) and
`TestConcurrentSweep` (1) — because `_set_status_timestamp` (`src/backend/conftest.py`) stamps
**`archived_at` only** for `ARCHIVED` and nothing else. Every case in that file creates
`status=ARCHIVED` rows with `published_at IS NULL`, which fails `published_at__lt=cutoff`.

`test_purges_manually_archived_recent_publish` is separately a **shipped green test whose
docstring pins the current anchor**: *"Proves delete_sweep anchors on `archived_at` (not
`published_at`): an ad published 10 days ago but archived 200 days ago must still be purged."*

**Consequence.** Fixing the file under options (i)/(ii) means editing
`src/backend/conftest.py::_set_status_timestamp` — **BLOCK 4's reserved file**. This is a **new
cross-block contention on the most contended file in the repository**, and the source plan does
not record it. It is a hard edge in §4 and a shared-artefact reservation in §5.

### C-16 / R-12 — the tripwire is mis-located and mis-attributed

`test_bulk_ban_users_not_locked` lives in
**`src/backend/apps/moderation/tests/test_admin_actions.py::TestBulkLockingStructure`** and its
docstring attributes it to **`DB-003` (phase 03)**: *"bulk_ban_users must NOT gain
select_for_update (out of DB-003 scope)"*. It is **not** in `apps/users/tests/` and **not**
phase 04's. The source plan attributes it to phase 04 in BLOCK 3 note 6, BLOCK 9 note 5, §5.3
and §7.

**Consequence.** The tripwire **still binds**. Only the attribution and location are corrected.
Following the source plan literally, an Implementor would search `apps/users/tests/` for a test
that is not there.

### C-17 / C-18 / C-19 — BLOCK 7's cross-phase boundaries are mis-scoped or vacuous

| # | Source plan says | Tree says | Consequence |
|---|---|---|---|
| **C-17** | `03-DB-008` owns per-batch commits for `delete_sweep`; three-way claim on the file | `e61555f`'s diff contains **only** `archive_sweep.py`, `recompute_normalized_prices.py`, their two test modules, `test_sweep_lock_structure.py` and two docs. **`delete_sweep.py` is not in it.** `db-retention.md:170–176` confirms the scope | BLOCK 7 has a **free hand** on the transaction shape. The source plan's `§8.4` DoD item *"single-transaction shape unchanged (phase 03 BLOCK 1 and BLOCK 7's)"* is **re-worded**: only the `storage_keys` half was ever phase 03's, and that half is already gone (C-18) |
| **C-18** | BLOCK 7 must not remove the redundant `storage_keys` pre-collection (`03-DB-011`) | `d913088` already removed it from `delete_sweep.py` (−14/+1) and five other sweeps. `delete_sweep.Command.handle` has **no** `storage_keys` reference; `test_collects_thumbnail_keys_for_media_cleanup` now asserts against `apps.media.signals.delete_photo` | The note is **MOOT — remove it** |
| **C-19** | `test_sweep_lock_structure.py` asserts `session is False` for **every** lock-taking command | It defines `_SESSION_SCOPED_BATCHERS = frozenset({"archive_sweep", "recompute_normalized_prices"})` and asserts, per command, `session is True` **and** `in_atomic is False` for those two, and **`in_atomic is True` and `session is False`** for the other eleven. **`delete_sweep` is in the transaction-scoped group** | `delete_sweep` remains constrained: BLOCK 7 **must not** convert it to per-batch commits, because that needs a session lock and would fail the assertion. The file also pins `EXPECTED_SWEEP_COMMANDS` by **name-set equality** — adding a lock-taking command without registering it fails |

### C-20 / R-4 — BLOCK 6's "no precedent exists" is FALSE

Plan BLOCK 6 note 3: *"There is no `AdAdmin` change-form test anywhere in the tree."* — True for
`AdAdmin` (zero matches tree-wide for `AdAdmin`, `admin.site`, `admin_client`, `admin:` reverses
across every `test_*.py`).

**But `src/backend/apps/users/tests/test_admin_change_form.py` (landed `a19a0ee`) is a full
admin-view HTTP test module** — `django.test.Client()` + `client.force_login(staff_user)` +
`client.get/post(reverse("admin:users_user_change", args=[target.pk]))` — described in
`a19a0ee`'s message as *"the first admin-view test in the repo"*.

**Consequence.** BLOCK 6's new `AdAdmin` change-form module **copies this pattern**: module-local
`staff_user`/`superuser` fixtures, `Client`, `force_login`,
`reverse("admin:ads_ad_change", …)`. `test_admin_pii_containment.py` (which uses `RequestFactory` +
`get_form()` introspection) is the **introspection alternative**, not the only option. **Both**
join BLOCK 6's keep-green list; the source plan names only the latter. A fresh Implementor
reading the source plan would conclude no harness exists and may invent one (R-4).

### C-21 / R-13 — an unlisted guard on BLOCK 3's edit surface

`src/backend/apps/moderation/tests/test_moderation_views.py::TestModerationReviewLocking` carries
**three** `inspect.getsource` guards asserting `"transaction.atomic" in source` and
`"select_for_update" in source` for `review.approve_ad`, `review.reject_ad` and `review.ban_user`.

**Consequence.** They survive a gate widening (both tokens are already present), but they must be
**listed and kept green** — exactly as `TestBulkLockingStructure` is. Otherwise an Implementor may
"simplify" the approve view's `atomic()`/`select_for_update()` pair while widening its filter. The
source plan's BLOCK 3 file surface names `TestApproveAdView` only.

### C-14 / R-8 — `db-schema.md` already asserts the post-`AD-009` behaviour

`docs/02-database/db-schema.md` already asserts the *fixed* behaviour of `AD-009`:
*"`published_at` is reset by `ad_reactivate` and price/photo edits too"*. `db-schema.md`'s
`published_at` comment (*"UPDATED on every PUBLISHED transition (timer reset)"*),
`original_published_at`'s (*"IMUTABLE, audit only"* — the line reads `IMMUTABLE`),
`docs/01-spec/technical-specification.md` decision J, and `Ad.published_at`'s own `help_text` all
already promise the fixed behaviour.

**Consequence.** BLOCK 2's documentation deliverable is a **verification, not an edit**. **The
doc must never be "corrected" backwards** to match the buggy code. BLOCK 2 makes the code match
the documentation — that is the correct direction.

### R-5 / R-14 — `03-DB-004` landed; a **fifth** non-success cause exists

`4db77ed`, `42d0edd`, `bb034e9` (`03-DB-004`) landed a connection-level `lock_timeout`.
`src/backend/apps/ads/views/edit.py` (`ad_edit`) and
`src/telegram_bot/handlers/ad_create/submit.py` (`process_preview`) **both** now catch
`OperationalError` + `is_lock_timeout` at the **handler** layer — `ad_edit` re-renders,
`process_preview` renders a busy message and **keeps** FSM state.

**Consequence.** `submit_ad` can now raise `OperationalError`. That is a **fifth** non-success
cause that `SubmitAdOutcome` must **not** absorb: the source plan's closed Q12 decision says
*"the lock timeout stays an exception — the enum houses business outcomes only"*, and that
decision remains correct. But the **boundary now lives partly in `03-DB-004`'s handlers**, so
BLOCK 12 **must not double-handle it**: if `submit_ad` grows a blanket handler it will re-handle
a condition the handler layer already owns (R-5). `R-14`: the source plan's five-member enum list
(`PUBLISHED`, `MODERATION_FAILED`, `PHOTO_UNAVAILABLE`, `DRAFT_GONE`, `INVALID_TRANSITION`) is the
correct set **and does not include it** — no change needed, but the boundary must be documented.

### Migration numbers — read the `.py` files, never `__pycache__`

| App | Last migration present | **Next free** |
|---|---|---|
| `src/backend/apps/ads/migrations/` | `0008_remove_ad_ix_ads_draft_sweep_ad_ix_ads_draft_sweep` | **`0009_*`** |
| `src/backend/apps/core/migrations/` | `0005_scheduler_daily_state` | `0006_*` |
| `src/backend/apps/media/migrations/` | `0001_initial` | `0002_*` |
| `src/backend/apps/moderation/migrations/` | `0001_initial` | `0002_*` |

**R-19.** `src/backend/apps/ads/migrations/__pycache__/` holds `.pyc` files for **nine
non-existent** migrations (`0003_ad_i18n_fields`, `0007_search_vector_i18n`,
`0008_search_vector_gin`, `0009_adfavorite`, `0010_ad_currency_price_fields`,
`0011_catalog_filter_indexes`, `0012_ad_listing_condition`, and others). A recursive-glob listing
reads a phantom set ending at `0012_ad_listing_condition` and generates a colliding number.
**The `.py` files present are the only authority. Do not read the migration set from
`__pycache__`.**

### R-7 — BLOCK 1's `VAL-001` deliverable is TWO bare IDs, not three

`DB-003`'s comment inside `Ad.transition_to` was rewritten by
`fd8c423 docs(core): make in-code finding-id citations resolvable (03-VAL-001)` to *"re-read from
DB to defeat stale-state races (DB vs. bot process, concurrent sweeps)"*. **Two** bare
cycle-unscoped IDs remain, both `AD-001`: one on the `ON_MODERATION_FAILED` edge comment, one on
the `DELETED` branch's *"last modified"* comment.

**A fourth bare ID exists outside BLOCK 1's file surface**:
`docs/02-database/db-schema.md`'s `archived_at` column comment
(*"drives delete_sweep timer (60d from archive, AD-005)"*). It is **recorded, not fixed** — the
repository-wide sweep of legacy citations is phase 03 BLOCK 11's and is gated on a coordinator
decision. An Implementor told "rewrite exactly those three lines" will look for a line that no
longer exists.

### R-9 — BLOCK 14's retirement record would contradict a shipped doc

`docs/02-database/db-retention.md` states *"Proper refcounting (AD-003) is still open."* That
contradicts BLOCK 14's `AD-003` retirement record, and `db-retention.md` is **not** in the source
plan's BLOCK 14 file surface. **This execution adds it to BLOCK 14's surface** (see §3 BLOCK 14).

### R-21 — `AD-015`'s `UserAdmin` half is already fixed

`AD-015`'s record must say the `UserAdmin` exposure half is **already fixed** by `a19a0ee`, not
"gone once phase 04 lands" and not "deferred". Writing "deferred" leaves a stale record in
BLOCK 14 and in the final report. The **behaviour** defect
(`ads_auto_publish=False` does not hide a published ad —
`ListingsQuery.build_queryset` still has no `ads_auto_publish` term) remains OPEN and unowned,
owned by phase 06 `PII-104` + `VAL-003` and phase 15 `AUTHZ-005`.

### R-10 — `AdvisoryLockId` has 19 members, not 18

`src/backend/apps/core/enums.py::AdvisoryLockId` (an `IntEnum`) has **19** members:
`ARCHIVE_SWEEP=1` … `ALERT_DELIVERY_TASK=9`, `PURGE_DELETED_ADS=11`,
`RECOMPUTE_NORMALIZED_PRICES=12`, `REPAIR_BOT_USERNAME=13`, `MIGRATE=100` … `CATALOG_LOAD=104`,
`SEED=110`, **`TEST_SCHEMA_SETUP=111`**. **ID 10 is unallocated.** The source plan's §5.1 "18
members" is stale; `TEST_SCHEMA_SETUP = 111` is newer. **Phase 05 allocates none.** If one is ever
forced, `enums.py`, the allocation table in `src/backend/apps/core/utils/advisory_lock.py`'s
docstring and `src/backend/apps/core/tests/test_advisory_lock_ids.py` change in **one** commit and
the coordinator is told first.

### R-11 — `_QUERY_BOUND` is 19, not 16

`src/backend/apps/ads/tests/test_ad_detail_queries.py` has `_QUERY_BOUND = 19`, with the module
comment *"Budget: 16 + SAVEPOINT + SET CONSTRAINTS + RELEASE SAVEPOINT = 19"* and an explicit
*"Do NOT re-tighten this to 16: that would re-break a correct fix."* The source plan still carries
`= 16` in BLOCK 2 note 7 and in §5.1. **Re-word; do not re-tighten.**

### C-24 — `technical-specification.md` attribution is unevidenced

The source plan's §5.2 attributes `docs/01-spec/technical-specification.md` to *"phase 06
`PII-113` is editing it"*. **`PII-113` does not exist in any commit.** Phase 06 has landed only
`PII-001`, `VAL-001`, `PII-002`. Four commits have touched that file, all from other work.
**The constraint is sound — no phase-05 block may edit that file. The attribution is wrong** and
must read *"reserved to phase 06; `PII-113` not yet landed"*.

### C-1 — the report's severity tally is arithmetically wrong and now more wrong

`1 CRITICAL · 4 HIGH · 8 MEDIUM · 3 LOW = 16` does not add up. Corrected to 14 live, and at the
anchor **three more items (`AD-005`, `AD-007`, `AD-012`) have left the open set**. The source
plan's §0.4 table and §8.1 disposition counts must be re-derived from §0.1 of **this** document.

### C-2 — `basedpyright` is at 0 errors

See the authority note at the top. **0 errors, 0 warnings, 0 notes**; scope fix is `8bf0517`.

### Corrections re-confirmed correct at the anchor (no scope change)

`C-4` (`AD-003`'s mechanism is an existence check, not a stored refcount) · `C-5` (`AD-011`'s
quoted evidence is not shipped code; the `PUBLISHED` branch nulls none of the three) · `C-6`
(`api_bulk.py` imports `approve_ad, reject_ad` from `apps.moderation.admin_actions`;
`bulk_approve(queryset, moderator_id)` takes a `QuerySet`, so *"call `bulk_approve`"* is
unexecutable) · `C-7` (`AD-008`'s "drop `ON_MODERATION`" branch must not be actioned before
`VAL-003`) · `C-8` (`AD-006` vs `MEDIA-002`) · `C-9` (`AD-012`'s DB half → `03-DB-009`) ·
source-plan §0.6.3 corrections **1** (`0009`), **2** (`ModeratorActionType` has **five** members:
`REJECT`, `BAN_ACCOUNT`, `SOFT_DELETE`, `CRITERIA_CHANGE`, `OTHER`), **3** (`AD-007` moot),
**4** (`submit_ad` has **three** `False` returns), **5** (BLOCK 12's `process_preview`
description is stale — confirmed and **understated**), **6** (the bulk endpoint's tests are
**one** class, `test_priority_service.py::TestBulkModerationActionView`, 22 methods), **7**
(`_pass_moderation` writes **two** `AnalyticsEvent`s; `set_published` writes zero), **8**
(`ModeratorActionLog` has **no moderator column** — `log_manual_publish(ad_id, moderator_id)`
persists nothing of `moderator_id`), **9** (`edit.html` advertises an inert photo control — a
tree-wide search for `request.FILES` returns **no matches in any `.py` file**), **10**
(`TestPublishedTextEdit` has **six** methods), **11** (`apps/ads/services/` has **no
`__init__.py`** — `apps/ads/__init__.py` exists, `services/` is an implicit namespace package, so
the source plan's "re-export through `__init__.py` and `__all__`" is unexecutable),
**12** (`transition_to` puts `updated_at` in `update_fields` only on the `DELETED`
short-circuit; `update_fields = ["status"]` is initialised for every other branch),
**13** (`_QUERY_BOUND = 19`).

### Two new findings filed by the code context — RECORD-ONLY, not executed here

| Candidate | What the tree shows | Disposition |
|---|---|---|
| **Inert photo control in `edit.html`** (`05-NEW-01` in the code context) | `src/backend/templates/ads/edit.html` has `<input type="file" id="images" name="images" accept="image/*" multiple …>` under `{% trans "Add Photos" %}` and the promise *"Price/photo changes will be published immediately."* No `request.FILES` anywhere in any `.py` | **RECORDED, not executed.** BLOCK 2's required *photo-only* test is **unimplementable** — there is no upload path. Record it and route it; do not build the upload path here |
| **All non-permission `ad_copy` failures collapse into one string** | `cmd_copy`'s `except Exception` renders a single generic string for ad-not-found, non-`PermissionError` permission failure and anything else | **RECORDED, not executed.** This is the residual BLOCK 11 describes — a **different, smaller** job. See §3 BLOCK 11 |

Neither is given a cycle number. **Never infer a cycle number** — prefer the descriptive form
over a guessed attribution (the source plan BLOCK 14 note 5's rule, applied to itself).

---

## §2. Owner gates — and how this execution handles them

**Five gates are product/owner decisions routed to the user through the coordinator: Q1, Q2,
Q4, Q5, Q6. This execution does not decide any of them, and neither may any agent inside it.**
Each is restated below with its options, its consequences, and — critically — **what ships
regardless of the answer**, so a gate that never closes does not deadlock the phase.

**A gate never closes silently.** If a gate is unanswered when the phase reports, the block is
recorded as **"open — deferred"** with the §4.4-style consequence written down, and that record
is a DoD item. Silence is not an acceptable outcome.

| Gate | Block | Owner | Ships regardless |
|---|---|---|---|
| **Q1** | BLOCK 6 | User / product, via coordinator | The four unconditional fixes + the `search_vector*` removal |
| **Q2** | BLOCK 5 | User / product, via coordinator | Nothing from BLOCK 5 — but BLOCK 3 and BLOCK 4 both ship |
| **Q4** | BLOCK 7 | User / product, via coordinator | The `db-retention.md` fragment repair; nothing else |
| **Q5** | BLOCK 8 | User / product, via coordinator | The allow-list conversion (this execution splits it — see §2 Q5) |
| **Q6** | BLOCK 13 | Coordinator | Nothing from BLOCK 13 — it becomes a cross-reference |

Two further gates are **not owner gates** but are **not closed either**: **Q7** (scope — routed
to the coordinator, non-blocking for BLOCK 12) and **Q8's value** / **Q10's value** (closed
inside the block by its Researcher/Planner step).

### §2 Q1 — May a moderator move an ad's status, and through which write path? → BLOCK 6

**Status: OPEN — not decided here.** Owner: user / product, via the coordinator.

**The gap is the seam, not the capability.** `docs/04-user-stories/admin-stories.md` US-A3
authorises the capability (*"Unpublish, delete, **change status**, or ban all of a user's ads.
Actions are instant and **logged to `ModeratorActionLog`**"*). `docs/02-database/db-schema.md`
declares `original_published_at` *"set once on FIRST publish; IMMUTABLE, audit only"*.
**No document says whether the Django admin change form is a supported moderation surface**,
and nothing distinguishes "a moderator may change status *through a sanctioned service*" from
"*by typing into the form*". That is what Q1 must resolve.

| Option | Consequence |
|---|---|
| **`status` stays editable** | The four unconditional violations are unfixed: no `ModeratorActionLog` row, mutable `original_published_at`, silent owner transfer, and two HTTP-500-class check-constraint failures. The state machine stays bypassable by any staff user with a browser |
| **`status` becomes read-only** | The sanctioned path must exist **first** or moderators lose the ability to publish entirely — this is the hard `3 → 6` edge. Depends on BLOCK 3 landing and BLOCK 6's internal ordering (read-only **last**) |

**Ships regardless of the answer:** the four unconditional fixes — (i) no audit row for an
admin-form status change, (ii) `original_published_at` must be immutable through the form,
(iii) `user` must not be reassignable through the form, (iv) the two HTTP 500s on `REJECTED` and
`ON_MODERATION_FAILED` POSTs — **plus** the removal of the four `search_vector*` fields from the
admin form (a form hygiene change, unrelated to `status`, and safe because the
`ads_search_vector_update` trigger neutralises manual edits). BLOCK 6 is **degradable, not
deadlock**.

**Deferred if unanswered:** the `status` read-only change. Recorded as **open — deferred**.

### §2 Q2 — Which side of `ON_MODERATION` durability does the business want? → BLOCK 5

**Status: OPEN — not decided here.** Owner: user / product, via the coordinator.

| Option | Consequence |
|---|---|
| **(i) Durable across transactions** | `ON_MODERATION` is committed, then moderating runs. US-S2 / US-A12 / US-A13 become true and the human queue becomes real. Requires a **recovery mechanism** — who re-drives an ad left in `ON_MODERATION`, and what happens if it never runs. **No document states how long a durable `ON_MODERATION` may persist, who re-drives it, or whether the seller sees it.** No timeout, sweep or re-drive contract exists anywhere |
| **(ii) Same transaction (status quo)** | Nothing changes in the writer; the human approval path stays dead for `ON_MODERATION` and only `ON_MODERATION_FAILED` is approvable. This is what the tree does today |
| **(iii) Drop `ON_MODERATION` from the durable set** | A state-machine change, and it must not be actioned before `VAL-003` is fixed (source plan C-7) |

**Ships regardless:** BLOCK 3 (the widen is correct under **all three** answers — under (iii)
`ON_MODERATION_FAILED` is the only status that survives, so the widen is the correct and only
fix) and BLOCK 4 (required before any future BLOCK 5). The phase therefore still delivers a test
suite that can actually validate `ON_MODERATION` and a working approve path — a strict
improvement over the audit baseline, with `AD-008` recorded as open-and-gated.

**Recorded as open — deferred** if unanswered: `AD-008`.

### §2 Q4 — The retention anchor → BLOCK 7

**Status: OPEN — not decided here.** Owner: user / product, via the coordinator.

**Four documents, two anchors.** `db-retention.md` says ARCHIVED is *"2 months (from
`archived_at`)"* and `delete_sweep` *"60 days (from archived_at)"*. US-S7 says *"4 months →
permanently removed. Timers count from `published_at`"*. US-A5 says *"delete @4 months (from
`published_at`)"*. Decision J says *"Archive/delete timers count from `published_at`"*. **The
tree matches `db-retention.md`** — the minority reading.

| Option | Consequence |
|---|---|
| **`GREATEST(published_at, archived_at)`** | Preserves both intents. **Breaks** `test_purges_manually_archived_recent_publish` — a shipped green test whose docstring pins the current anchor |
| **`published_at` only** | Matches US-S7, US-A5 and decision J. **Breaks the same test.** Also `published_at IS NULL` rows never qualify |
| **`archived_at` (status quo)** | Matches the tree and `db-retention.md`. Leaves three documents disagreeing, and `AD-004` open |

**Ships regardless:** the cosmetic `db-retention.md` repair — the duplicated fragment that reads
*"Finds all ads with `status = 'DELETED'` and `deleted_at` older than / `deleted_at` is older
than 120 days"* is a **one-line defect in a file BLOCK 7 already edits**, and it is live. It is
shipped as part of BLOCK 14's documentation work (§3 BLOCK 14), not gated on Q4, because
touching the file at all is required once Q4 lands.

**Deferred if unanswered:** the anchor half, the predicate, and the migration. **This is the one
HIGH in the phase that cannot be partially delivered** — "correct" is undefined without the
answer. Recorded as **open — deferred** in BLOCK 14.

### §2 Q5 — The product rule for editing a failed ad → BLOCK 8

**Status: OPEN — not decided here.** Owner: user / product, via the coordinator.

**What is stated nowhere:** whether a failed ad is re-moderable, whether the 7-day
`purge_failed_ads` timer may be reset by a resubmission, and whether an "Edit" affordance
should be shown for a status where edit cannot succeed. **No user story says.**

| Option | Consequence |
|---|---|
| **(a) Hide the dead end** | The dashboard Edit link is gated and the branch refuses. Does **not** reset the purge timer — the ad is still purged, only now with a message. `AD-002` is hidden, not fixed |
| **(b) Allow re-moderation** | The ad returns to moderation, `moderation_failed_at` is reset. **Requires adding `ON_MODERATION_FAILED → ON_MODERATION` to the matrix** — `ALLOWED_TRANSITIONS[ON_MODERATION_FAILED]` is `{REJECTED}` today. **Retry bounding is part of the option**, or a seller can reset the 7-day timer forever |
| **(c) Hide and purge sooner** | Also a hiding fix |

**Ships regardless — and this is a deliberate split the source plan only proposed.** The
source plan's §4.4 says *"The Planner may propose that split; this plan does not decide it."*
**This execution proposes and adopts it:** replacing the `else:` catch-all with an **explicit
status allow-list** is a pure structural fix — it makes the branch's behaviour *defined* for all
seven statuses and removes the catch-all the validator forbade — and it is **independent of
Q5** because it changes no product rule, only the enumeration. It lands as **BLOCK 8A** (§3).
The Q5-dependent rule lands as **BLOCK 8B** and waits.

**Deferred if unanswered:** the failed-ad re-moderation rule, the purge-timer interaction, and
the dashboard link gating.

### §2 Q6 — `AD-006` (MEDIUM, phase 05) vs `MEDIA-002` (HIGH, phase 07) → BLOCK 13

**Status: OPEN — not decided here.** Owner: coordinator.

**One predicate, two records, two remediation descriptions that are not obviously the same
patch.** `AD-006`'s minimal fix re-scopes the lookup to `(ad, sha256)`. `MEDIA-002`'s
described fix **reclaims the skipped file** — a fresh row under a freshly generated unique key.
Phase 07's own plan rates `MEDIA-002` HIGH, orders it **first** in its rollout, and states that
landing it first *"removes the accidental-aliasing vector entirely"*. It also states that
phase 05's BLOCK 13 **ships no production code** if its plan lands first.

**The gate is genuinely live at the anchor.** `MEDIA-002` has **not** been executed:
`AdImageService.create_or_skip` still filters `ad__user_id=ad.user_id` with a *"Deduplication is
scoped per seller"* docstring, and `submit_ad` still discards the return value.

| Answer | Phase-05 action |
|---|---|
| **`MEDIA-002` is the record** | **BLOCK 13 ships no production code.** It becomes a cross-reference, a check that phase 07's fix covers the ads-side call site, and a record in BLOCK 14. Shipping the minimal `AD-006` fix **alongside** `MEDIA-002` produces two patches for one predicate — the exact hazard `VAL-004` was raised to prevent |
| **`AD-006` is the record** | BLOCK 13 ships the ads-side fix and phase 07 must re-scope `MEDIA-002` to the media-side half. **Which half is left must be stated**, because the two descriptions are not the same patch |

**The tie-breaker the owner needs.** A duplicate is detected **after**
`move_staging_to_permanent` has already moved the file, and `submit_ad` discards the returned
row — so the promoted file is on disk with **no** `AdImage` row pointing at it, reclaimed later
by `sweep_orphaned_media`. **Re-scoping the lookup alone does not fix that**; it makes it the
*normal* case, because a seller posting the same photo to two ads is no longer unusual.
Whichever record wins **must state whether it addresses the orphan**.

**Ships regardless:** nothing production-side. The recorded tie-breaker and the recorded gate are
themselves the deliverable.

### §2 Q7 — is `_pass_moderation`'s bare handler a phase-05 finding?

**Status: OPEN — routed to the coordinator, non-blocking.** `auto_moderation.py::_pass_moderation`
catches `MaxAdsExceeded` **and a bare `except Exception`**, calling `_fail_moderation(ad)` on
either — so a **database error during publish is reported to the seller as** *"Ad failed
moderation. Please check your content and try again."* A system failure becomes a content
verdict.

This defect class is not in the source report. Q7's only effect is the **size** of BLOCK 12:
fold the branch in, file it as a new finding owned by phase 03, or defer it. **BLOCK 12 ships
whichever way it goes, and the disposition is recorded in the commit message even if the answer
is "deferred".**

**Two binding constraints this execution adds.** (i) Q7 **must be answered before BLOCK 5 option
(i) ships** — under (i) the failure would cross a transaction boundary. (ii) **BLOCK 12 must not
absorb `OperationalError`.** `03-DB-004` landed that handling at the **handler** layer in
`ad_edit` and `process_preview`; `submit_ad` can raise it and the handlers own it (R-5, R-14).

---

## §3. Execution blocks

**Rules that apply to every block below.**

- **Exactly one Implementor at a time.** The order in §4 is serial.
- **Every target is a semantic symbol** — file plus `module` / `class` / `function` / `method` —
  never a line number (`.ai\tasks\templates\task_template.yaml`).
- **Every task YAML** is shaped by that template and carries
  `source_reference: .ai\plans\17-ad-lifecycle-execution.md` and
  `source_section: "BLOCK N — <title>"`.
- **Tests verify logic and component interaction** — never the absence of a variable, a log
  string, or a line count. BLOCK 1's matrix-identity test is the boundary case: it asserts a
  *value*, not a line count, and it is legitimate because the extraction is a refactor with no
  other observable.
- **Project rule 2** — if a test conflicts with the architecture or the business logic, fix the
  test, never the production code. Every rewrite below names its reason.
- **Staging** — explicit paths only. Re-read `git status --short` immediately before every
  commit. Never `git add -A`, `git add .`, `git commit -a`, `git reset`, `git checkout`,
  `git stash`, `git clean`.
- **Commit only on explicit user request.**

### BLOCK 1 — Hoist the transition matrix, and make timestamp clearing uniform

| | |
|---|---|
| **Findings owned** | `AD-013`, `AD-011`, the `Ad.transition_to` half of `VAL-001` |
| **`depends_on`** | — |
| **Priority** | P0 (BLOCKs 2, 6 and 8 all build on the matrix being inspectable) |
| **Readiness** | **READY-WITH-CORRECTIONS** |

**Corrections absorbed** (§1): R-7 — the `VAL-001` deliverable is **two** bare IDs, not three
(`DB-003`'s comment was rewritten by `fd8c423`). A **fourth** bare ID sits at
`docs/02-database/db-schema.md`'s `archived_at` comment and is **recorded, not fixed** — the
repository-wide citation sweep is phase 03 BLOCK 11's and is gated on a coordinator decision.

**Grouping decision (carried from the source plan).** `AD-013` is a pure extraction and `AD-011`
is a one-branch behaviour change. They are one block because they are **the same edit surface**
— the body of `Ad.transition_to` — and because `AD-009` (BLOCK 2) needs both: it must not add a
third divergent timestamp-clearing idiom.

**Agent roster.**
- **Implementor — yes.** Always; exactly one at a time.
- **Auditor — yes.** Must re-derive every caller of `transition_to` at the anchor and confirm
  none depends on the matrix being a local (e.g. via `inspect.getsource`), and confirm no other
  module defines a competing transition map. This is the only way the extraction is provably
  behaviour-preserving.
- **Validator — yes.** A refactor's entire risk is *behaviour change you did not intend*. An
  independent review of the extracted matrix against the original literal, character for
  character, is the only real control.
- **Researcher — NO.** No modern-practice or multi-approach question. Project rule 10 already
  names the shape, and the tree already shows the model. A Researcher pass adds latency and no
  information.
- **Planner — NO.** The design is fully determined by the finding: extract verbatim, add one
  field to one branch, add one string to one `update_fields` list. There is nothing to design.

**Decision gates carried: none open.** (Q3's shape is closed at the source plan §0.6 and lands
in BLOCK 2, not here.)

**File surface (semantic units).**
- `src/backend/apps/ads/models.py` → module scope above `class Ad` (the **new** module-level
  `ALLOWED_TRANSITIONS` annotated value); `class Ad` → `transition_to` (the matrix literal, the
  `PUBLISHED` branch, the `update_fields` accumulation, **two** audit-ID comments).
- `src/backend/apps/ads/tests/test_ad_constraints.py` → `class TestStatusTimestampConstraints`.

**Constraints.**
1. The extraction is **character-for-character identical**. No new edges, no reordered keys, no
   silent `set()` → `frozenset()`. `AD-013` is a **zero-behaviour-change** block and every
   existing matrix test must pass **untouched**. `ALLOWED_TRANSITIONS` has **7** source keys.
2. The two special cases stay **outside** the matrix: `DELETED → *` raises a `ValueError` before
   the matrix is consulted, and `* → DELETED` short-circuits past it (setting `deleted_at` **and**
   `updated_at`). Folding either in stops this being a refactor.
3. The type annotation `dict[AdStatus, set[AdStatus]]` moves with the value. `AdStatus` is already
   imported by the module.
4. `AD-011`'s fix is **one assignment plus one `update_fields` entry** in the
   `target == AdStatus.PUBLISHED` branch. The list is built incrementally, so an assignment
   without the append is a **silent no-op** — the single most likely way this ships broken while
   looking correct.
5. Only `ARCHIVED → PUBLISHED` is affected. The `ON_MODERATION` branch already nulls
   `archived_at`. Do **not** unify the branches — that is a design change beyond the finding and
   `VAL-006`'s write-path decision is where it belongs.
6. `refresh_from_db()` is the method's **first statement** and is load-bearing (defeats
   stale-state races; raises `Ad.DoesNotExist` if a sweep hard-deleted the row). Nothing in this
   block may move it.
7. `update_fields` contains `updated_at` **only** on the `DELETED` short-circuit;
   `update_fields = ["status"]` is initialised for every other branch.

**Tests required.**
- *Must be added:* in `TestStatusTimestampConstraints`, a case asserting a row in a non-`ARCHIVED`
  status carrying a stale `archived_at` is **rejected by the database** — the direct guard for
  the `ARCHIVED` → `PUBLISHED` round trip. Assert on a **freshly reloaded instance**, never the
  in-memory object, which would pass even if `update_fields` were wrong.
- *Must be added:* a matrix-identity test asserting module-level `ALLOWED_TRANSITIONS` is
  importable from `apps.ads.models` and that its seven source keys and target sets match the
  shipped matrix exactly.
- *Must keep passing unchanged:* `test_ad_lifecycle.py` → `TestTransitionValidation`,
  `TestTransitionMatrixEdges`, `TestOriginalPublishedAtImmutability` (both cases),
  `TestPublishedAtUpdates::test_published_at_updates_on_re_publish`; `test_ad_constraints.py` →
  `TestMutualExclusivityConstraint` and the existing one-way cases;
  `test_transition_concurrency.py` in full.
- *Explicitly not to change:* `test_published_at_updates_on_re_publish` asserts nothing about
  `archived_at` and passes either way.

**Docker gate command.**
```
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/ src/telegram_bot/tests/test_ad_lifecycle.py" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```
where `$dc` = `docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml`.

**Risk / rollback.** A missed `update_fields` append ships as a silent no-op (mitigation: the
reloaded-instance test). A non-verbatim extraction changes an edge (mitigation: the
matrix-identity test). The audit-ID rewrite is read as "starting the legacy sweep" (mitigation:
the file surface is bounded to this one function). **Rollback:** trivial — one production file,
no migration, no data.

---

### BLOCK 2 — A price or photo edit must restart the publish clock

| | |
|---|---|
| **Findings owned** | `AD-009` |
| **`depends_on`** | **BLOCK 1** (hard) |
| **Priority** | P1 |
| **Readiness** | **READY-WITH-CORRECTIONS** |

**Corrections absorbed** (§1): **C-14 / R-8** — `db-schema.md` **already asserts** the
post-`AD-009` behaviour, so the documentation deliverable is a **verification, not an edit**,
and the doc must **never** be corrected backwards. **R-11** — `_QUERY_BOUND` is **19**, not 16,
with an explicit *"do NOT re-tighten"* comment. The source plan's required **photo-only** test
is **unimplementable**: `edit.html` advertises a `multiple` file input and no `request.FILES`
exists anywhere in any `.py` file — **recorded as a new finding, not executed here** (§1).

**Agent roster.**
- **Implementor — yes.**
- **Auditor — yes.** Must re-derive the `PUBLISHED`-and-not-`has_text_change` branch at the
  anchor, confirm `published_at` is absent from its `update_fields`, and confirm **no other
  path** bumps `published_at` on a price edit — a second writer would make the fix ambiguous.
- **Researcher — NO.** Q3 is **already closed** (below). There is no open technical question.
- **Planner — no.** The design is closed by Q3's decision; what remains is executing it.
- **Validator — yes.** The change silently alters a **retention clock**. A wrong choice either
  auto-archives an ad the seller just priced (a live listing disappears) or leaves the clock
  stale. Neither failure is visible in the suite unless a test asserts the new behaviour.

**Decision gate — Q3. CLOSED by the source plan §0.6.1. Recorded, not re-opened.**

> **Closed decision: Option B′.** `Ad.reset_publish_clock(update_fields: list[str]) -> None` —
> sets `published_at` and appends `"published_at"` to the **caller's** list;
> `transition_to`'s `PUBLISHED` branch calls it; `ad_edit` keeps exactly **one** `save()`.
>
> **Rationale.** The argument is non-negotiable: without it the caller must remember the field
> name, and an assignment without the append is a silent no-op. The matrix self-edge (the source
> plan's Option A) is **rejected on evidence**: `apps/moderation/signals.py::deliver_immediate_alerts_on_publish`
> does not inspect `update_fields`, and `apps/search/services/immediate_alerts.py::deliver_immediate_alerts`
> submits the send asynchronously with `record_notifications(ignore_conflicts=True)` and the
> receipt written **after** the send. A second `post_save` in the same transaction therefore
> registers a second `on_commit` and can produce a **duplicate Telegram message** for any
> saved-search pair still at `delivered_at IS NULL`. Plain Option B (a method that saves) has
> the same two-`post_save` problem.
>
> **Not to be re-opened by any Implementor.** If the Implementor believes this decision is
> wrong, that is a Planner-level escalation, not a local choice.

**File surface (semantic units).**
- `src/backend/apps/ads/models.py` → module-level `ALLOWED_TRANSITIONS` (BLOCK 1's output) and
  the new `Ad`-level `reset_publish_clock` method.
- `src/backend/apps/ads/views/edit.py` → `ad_edit` (the `status == AdStatus.PUBLISHED` branch
  that is not `has_text_change`); `_apply_price_change` (**read only**).
- `src/backend/apps/ads/tests/test_edit.py` → `class TestPublishedTextEdit`.
- Docs: `docs/02-database/db-schema.md` — **verification only** (C-14).

**Constraints.**
1. The defect is a documented spec deviation, not a wording ambiguity: decision J, the model's
   own `published_at` `help_text` and `db-schema.md` all already promise the behaviour.
2. **The block must not assume the Q4 anchor.** `archive_sweep` measures 60 days from
   `published_at`. Resetting the clock on a price edit is correct under **every** candidate
   anchor, which is why BLOCK 2 is not blocked on Q4. **Changing the window is BLOCK 7's job**
   and must not appear here.
3. The new method interacts with `AD-011`: on a price-only edit of a `PUBLISHED` ad,
   `archived_at` is already `None` (BLOCK 1 guarantees it), so this is a harmless no-op. **State
   it in the commit message; do not add a guard.**
4. The price fields and `published_at` are written in **one** `save(update_fields=[...])`. The
   view already owns the `atomic()`.
5. The documentation direction is **code matches documentation** (C-14). `db-schema.md` must not
   be edited to match the buggy code.

**Tests required.**
- *Must be **rewritten***: `TestPublishedTextEdit::test_edit_published_price_only_stays_published`
  — its docstring (*"PUBLISHED ad with price-only change -> stays PUBLISHED, **published_at
  unchanged**"*) and its `published_at` assertion both change. **Reason (project rule 2):** the
  test encoded the defect; production code is king. Name the reason in a comment.
- *Must be added:* a price-only edit of a `PUBLISHED` ad leaves the status `PUBLISHED` **and**
  moves `published_at` **strictly forward**, asserted on a reloaded instance.
- *Must be added:* a test proving the sibling text path still **preserves** `published_at` when
  the ad goes to `ON_MODERATION`.
- *Must be added:* a test that `original_published_at` is **not** overwritten by the re-published
  ad — `TestOriginalPublishedAtImmutability` covers this and must pass unchanged, but the new
  path must be shown to reach it.
- *Must keep passing unchanged:* the rest of `TestPublishedTextEdit` (**six** methods —
  `test_edit_published_text_edit_transitions_to_on_moderation`,
  `test_edit_published_price_only_stays_published` (the rewrite),
  `test_edit_published_mixed_edit_transitions_to_on_moderation`,
  `test_edit_published_text_edit_calls_auto_moderate`,
  `test_edit_published_text_edit_passes_auto_moderation`,
  `test_edit_published_text_edit_fails_auto_moderation`) — **touching any of the other five is a
  scope breach**; `test_ad_lifecycle.py` in full; **`test_ad_detail_queries.py` (run it — the
  budget is `_QUERY_BOUND = 19`, do not re-tighten)**; `test_sweep_delete.py` and
  `test_sweep_lock_structure.py` (no sweep change here).

**Docker gate command.**
```
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/ src/backend/apps/core/tests/" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```

**Risk / rollback.** The new method is later read as "a transition happened" and double-counts
(mitigation: the commit message names the constraint; `update_fields` is specified explicitly).
A live listing is auto-archived hours after being priced, because the clock moved and
`archive_sweep` is hourly — this is **intended behaviour under every candidate anchor**, and the
commit message must say so. The test rewrite is "fixed" by reverting production code
(mitigation: project rule 2 restated). **Rollback:** the code half and the test half revert
**together**; reverting one leaves either a red suite or a hidden defect.

---

### BLOCK 3 — Restore the human approval path

| | |
|---|---|
| **Findings owned** | `VAL-003` |
| **`depends_on`** | — (**must land before BLOCK 6**) |
| **Priority** | P0 — the most important block in the phase |
| **Readiness** | **READY** |

**Corrections absorbed** (§1): **C-21 / R-13** — `TestModerationReviewLocking` (three
`inspect.getsource` guards on `review.approve_ad` / `reject_ad` / `ban_user`) is an **unlisted
guard** and joins the file surface and the keep-green list. **C-16 / R-12** — the bulk-ban
tripwire is in `apps/moderation/tests/test_admin_actions.py`, attributed to **phase 03
(`DB-003`)**, not phase 04 and not `apps/users/tests/`.

**Why this block is first.** `AD-001`'s obvious fix is `AdAdmin.status` → read-only. That is
**catastrophic if it lands alone**: `bulk_approve` filters a status the system never commits,
the approve view 404s, and `approve_ad` returns `False` for every real ad. Ship read-only first
and **moderators lose the ability to publish entirely**. This block is the precondition; the
`3 → 6` edge in §4 is the second, independent guard.

**The failure is decidable independently of Q2.** `bulk_reject` and the review **detail** view
already filter `status__in=[ON_MODERATION, ON_MODERATION_FAILED]`. **The approvable set is
already defined in this codebase, twice, by the two paths that work.** The defect is that the
approve path was written against a narrower set than its own siblings use — so widening the
three approve gates is correct under **all three** Q2 answers, including (iii).

**Agent roster.**
- **Implementor — yes.**
- **Auditor — yes.** Must re-derive every gate filtering on a single ad status at the anchor and
  confirm the widen-narrow symmetry. **A missed gate means the path is still dead after the
  fix**, and the block would ship "restored" on an unverified claim.
- **Researcher — yes.** The durable-state semantics of a moderation queue have more than one
  defensible shape, and the answer determines whether BLOCK 5's work is a small widening or a
  redesign.
- **Planner — yes.** A cross-app change that must preserve the response shapes, the
  `ModeratorActionLog` writes and four shipped tests. It needs a written per-gate design before
  code — in particular **what the widened gate does when the target transition is refused**.
- **Validator — yes.** Highest risk in the phase. The failure mode is **silent**: a missed gate
  leaves the queue at 0 and the view at 404, and nothing in the suite notices.

**Decision gates carried: none owner-gated.** The per-gate design (including the
refused-transition behaviour) is a Researcher/Planner question closed **inside** this block and
recorded in the commit message.

**File surface (semantic units).**
- `src/backend/apps/moderation/admin_actions.py` → `bulk_approve` (its status filter),
  `approve_ad` (its status guard). `bulk_reject`, `bulk_ban_users`, `bulk_delete`,
  `soft_delete_ad` — **read only**.
- `src/backend/apps/moderation/views/review.py` → the `approve_ad` view's `get_object_or_404`
  gate. `moderation_review` (the detail view) is **already correct and must not change**.
- `src/backend/apps/moderation/services/priority.py` → `PriorityService.get_queued_ads`,
  `get_priority_counts` — **read only** unless the design changes their contract.
- `src/backend/apps/ads/admin.py` → `AdAdmin.action_approve` — **read only**; the button stays.
- `src/backend/apps/moderation/tests/test_moderation_views.py` → `class TestApproveAdView`;
  `class TestModerationReviewLocking` (**keep unchanged** — C-21).
- `src/backend/apps/moderation/tests/test_admin_actions.py` → `class TestBulkOperations`
  (retarget one case); `class TestBulkLockingStructure` (**keep unchanged** — the guard).
- **Not touched:** `apps/analytics/services/moderation_analytics.py::get_pending_queue_size`
  (Q2 decides what it means); `AdAdmin.readonly_fields`.

**Constraints.**
1. **Do not route manual approval through `auto_moderate`.** It would re-apply the *automatic*
   criteria over a decision a human has already made, and would **fail** an approve the
   moderator deliberately overrode. Contradicts US-A3's *"Actions are instant"*.
2. **`ON_MODERATION_FAILED → PUBLISHED` is refused by the matrix** (`{REJECTED}` only) and that
   is correct. **The state machine is not the thing to change here.** The block must state, in
   writing, what the widened gate does when the transition is refused — the honest answer is to
   **surface the state machine's own error to the moderator**, not swallow it and not 500.
3. **The `ModeratorActionLog` write must not be lost.** Widening the filter changes *which* ads
   reach the audit write, never *how* it runs.
4. **The source-inspection guard constrains the fix's shape.** Any rewording dropping
   `"select_for_update"`, `"order_by"` or `"pk"` from `inspect.getsource(bulk_approve)` turns the
   guard red — and the guard asserts a real invariant.
5. **This block must not delete `action_approve`** — that is Q1's territory (BLOCK 6).
6. **Do not add an alert.** No Prometheus is deployed; a `pending_moderation` alert is dead on
   arrival. If phase 12's `OPS-003` lands first, **carry the warning forward** — a new alert on
   a queue this block restores would fire on real numbers for the first time.
7. **The bulk-ban tripwire binds** (C-16): `bulk_ban_users` must **not** gain
   `select_for_update`.

**Tests required.**
- *Must be **rewritten***: `TestApproveAdView::test_approve_non_moderation_ad_returns_404` —
  **this one is the finding, written as a test.** The new test asserts what actually happens for
  a genuinely un-approvable status (`PUBLISHED`, `DELETED`, `DRAFT`) and must be demonstrated
  **red** against the pre-fix code for the `ON_MODERATION_FAILED` case.
- *Must be **retargeted** (not deleted):* `TestApproveAdView::test_approve_transitions_to_published`
  and `::test_approve_creates_moderation_log`;
  `TestBulkOperations::test_bulk_approve_publishes_all`. Each must reach its state through a
  status production can actually produce — `ON_MODERATION_FAILED` is reachable today via a real
  failing `submit_ad`. **Do not leave them fabricating `ON_MODERATION`.**
- *Must be added:* `bulk_approve` on a queryset containing a genuinely-approvable ad returns a
  **non-zero** count, with a `ModeratorActionLog` row and `published_at` written — the finding's
  direct regression guard.
- *Must be added:* the approve view returns **2xx** (not 404) for an approvable ad and performs
  both the transition and the audit write.
- *Must be added:* a status outside the approvable pair is **rejected with an actionable
  message** and writes **no** audit row.
- *Must be added:* the **refused-transition** case — the state machine's `ValueError` reaches
  the moderator as a message, not a silent no-op and not a 500.
- *Must keep passing unchanged:*
  `TestBulkLockingStructure::test_bulk_approve_uses_select_for_update_orderby_atomic` and all
  **five** of its methods (including `test_bulk_ban_users_not_locked`, phase 03's);
  `TestBulkOperations`'s `bulk_reject` cases; `TestModerationReviewLocking` (all three guards);
  `test_moderation_log.py`; every existing `ModeratorActionLog` assertion.

**Docker gate command.**
```
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/moderation/tests/ src/backend/apps/ads/tests/" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```

**Risk / rollback.** The block ships claiming the path is restored and a gate was missed —
mitigation: the non-zero-count and 2xx tests are **mandatory** and must be demonstrated **red**
first. The widen is over-read as "a moderator may approve anything" — mitigation: the pair is
the pair the codebase already defines twice. A newly reachable status bypasses the audit write —
mitigation: the audit-row assertions stay green plus a new one for the reachable status.
**Rollback:** one commit, no migration. Reverting restores the dead path, which BLOCK 6 must
not ship into — **if BLOCK 3 is rolled back, BLOCK 6 must be rolled back with it.**

---

### BLOCK 4 — Make the test suite reach `ON_MODERATION` the way production does

| | |
|---|---|
| **Findings owned** | `VAL-002` |
| **`depends_on`** | BLOCK 3 (soft — shared test files with BLOCK 3's retargeting); **hard-precedes BLOCK 5** |
| **Priority** | P0 — the rollout-safety precondition for BLOCK 5 |
| **Readiness** | **READY-WITH-CORRECTIONS** |

**Why this block exists separately.** `VAL-002` is not a production defect; it is a defect in
the **oracle**. If BLOCK 5 lands first, roughly half the fabricated tests stay green — they now
pass against a state that has become real — so the suite would report success while having
validated **nothing** about the durability path. The migration lands first, in its own commits,
so BLOCK 5 has a suite that can actually fail.

**Corrections absorbed** (§1): **C-22 / R-2** — **one** definition site, not two; the bot conftest
does not redefine the fixtures and `pythonpath` shares them. The source plan's two-conftest hard
requirement is **void**. **C-3** — the census is **63 omission sites in 7 files** (62 backend + 1
bot); the report's grep now returns **40** (2 production, 1 cleanup, 37 test); **560 of 622**
backend sites already pass `status=`; and there is a **ninth taxonomy class** — 9 test sites
fabricate through `transition_to(AdStatus.ON_MODERATION)`.

**Agent roster.**
- **Implementor — yes.**
- **Auditor — yes.** Must produce and record the **census** (below) at the anchor. The counts in
  §1 are measured; the **per-site classification** is not, and it determines the block's size.
- **Researcher — yes.** The taxonomy — which fabricated sites are *legitimate* (a test of the
  moderation queue legitimately needs a pending row) versus *illegitimate* (a test of the
  auto-moderation pipeline that fabricates the state instead of driving it) — is a real judgement
  with a large blast radius.
- **Planner — yes.** The largest mechanical change in the phase. It needs a written triage rule
  before code, and the rule must be applied consistently.
- **Validator — yes.** The failure mode is a suite that is green for the wrong reason —
  precisely the failure this block exists to eliminate. Independent review must confirm the
  census was complete and **no fabrication channel survives**.

**Decision gate — Q10. Mechanism CLOSED; the value is OPEN and is this block's Planner step.**

> **Closed (mechanism).** Change the default **first**, in its own commit, so the silent channel
> becomes loud failures and **the failure list *is* the migration map**.
>
> **OPEN — the value.** This execution does **not** pre-choose it. The options and consequences:

| Candidate | What it converts silently into failures | Consequence |
|---|---|---|
| **`PUBLISHED`** | The 63 omissions become visible; most are in `test_price_normalizer.py`, `test_priority*.py`, `test_auto_moderation.py`. `_set_status_timestamp` already sets `published_at`, so constraints are satisfied | Largest failure list, but those tests are about **published listings** and are green *by accident* of a default nobody chose. The source plan's code-context reading **recommends** this — **not decided here** |
| **A required keyword** (`status: AdStatus` with **no** default) | Every omission becomes a `TypeError` at collection time | Maximum clarity, and it makes the entire remaining census loud. But it is a large noisy diff across every test file in the repository, including files no phase-05 finding touches — the scope-creep shape project rule 7 warns against |
| **`DRAFT`** | Same count | **Rejected on evidence:** `Ad.Meta.constraints` declares `uq_ads_single_draft_per_user` (`UniqueConstraint` on `user_id`, conditional on `status=DRAFT`), so `create_test_ads_bulk` would start colliding. Actively worse |

**Mandatory internal order.**
`(a)` census (Auditor) → `(b)` change the fixture defaults in
**`src/backend/conftest.py` only**, commit — *red by construction* → `(c)` read the failure list,
apply the triage rule per file, commit → `(d)` retarget category (b) producer tests, commit →
`(e)` re-run the full fast gate, green → `(f)` record the census and the triage.

**Triage rule.**
- **(a) Consumer test** — tests a surface that *reads* `ON_MODERATION`. May legitimately need a
  pending row; after BLOCK 5 the state is real, so a directly created row is honest. **Needs no
  rewrite.** If a consumer test needs editing to survive the default change, it was
  **mis-classified** — revisit the classification *before* the edit.
- **(b) Producer test** — tests a surface that *writes* `ON_MODERATION` (`submit_ad`,
  `ad_reactivate`, `auto_moderate`). Fabricates instead of drives. **Must be retargeted**: either
  drive the real path and assert the **observable outcome** (published or failed), or — if the
  test is specifically about the transition *into* `ON_MODERATION` — rewrite it to assert the
  durable post-BLOCK-5 state once that state exists.
- **(c) Incidental** — a row created for an unrelated assertion. Get an explicit `status=` so it
  stops depending on the default at all.
- **(d) Matrix-valid fabricator** — the **ninth class** the source plan does not name. The 9
  Channel-C test sites reach `ON_MODERATION` through the **real** matrix edge from
  `DRAFT`/`ARCHIVED`, and in a test they commit. They are neither (a) nor (b): they are
  **matrix-valid but transaction-boundary-bypassing**. A three-class taxonomy does not cover
  them. Classify and record them separately; do not mechanically rewrite them.

**File surface (semantic units).**
- `src/backend/conftest.py` → `create_test_ad`, `create_test_ads_bulk`. **`_set_status_timestamp`
  — READ ONLY, it must not change here** (BLOCK 7 changes it under Q4 (i)/(ii); see §4).
- Every test file the census implicates — the exact list is the census output and is **not**
  enumerated here because the tree drifts; the block's `extra_context` carries it.
- **Not touched:** any production module; **`src/telegram_bot/tests/conftest.py`** (C-22).

**Constraints.**
1. **Change only the `status` default** (and any docstring describing it). **No other fixture,
   no other parameter, no formatting.** This file is the most contended in the repository;
   phase 03's plan states phase 03 **must not edit it at all**, and that is respected — phase 05
   edits it only because `VAL-002` *is* its fixture default. Re-read immediately before editing;
   stage by explicit path.
2. `_set_status_timestamp` is why the default has never broken a constraint. The default change
   therefore reds **assertions**, not `IntegrityError`s. **Understand this before chasing a
   phantom.**
3. **A failing suite is an expected intermediate state.** The red commit is never pushed alone;
   the internal order ends green and the block is never closed mid-sequence.
4. **Over-rewriting category (a) is scope creep** — the exact risk the Auditor's classification
  exists to prevent.
5. **This block must not change production code.** If a failure reveals a production defect that
   is not `ON_MODERATION`-related, record it and route it.
6. **Do not run the nightly `seed` suite.** `PYTEST_SKIP_MARKERS=seed` throughout.

**Tests required.**
- *Must be added:* a regression guard that **no** test fabricates `ON_MODERATION` through the
  fixture without an explicit, justified `status=` — so a future default change cannot silently
  re-open the channel. **Must be red against the pre-fix conftests.** This guard tests a
  **property of the suite's own contract**, not a variable's absence.
- *Must be added:* the convention recorded as a comment in `conftest.py` naming why the default
  is not `ON_MODERATION`.
- *Must be retargeted:* every category (b) producer test, plus the classification of the nine
  category (d) sites.
- *Must keep passing unchanged:* every category (a) consumer test, **without edits**.
- The block adds no test for its own sake; its deliverable **is** the suite's fidelity.

**Docker gate command.**
```
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```
(the **full** fast suite — the census is a whole-suite property, not a file property)

**Risk / rollback.** The default change lands alone and leaves the repository red (mitigation:
the internal order; the block is never closed mid-sequence). Over-rewriting inflates the diff
across a dozen files (mitigation: the Auditor classifies, the Implementor applies).
`conftest.py` is edited on a stale read (mitigation: re-read immediately before, explicit
paths). **The risk that would silently defeat the phase:** the census is narrower than reality
(mitigation: the Auditor re-measures; the block records the number it found; BLOCK 5's green
state must come **after** a recorded red baseline). **Rollback:** revert in reverse order —
rolling back the default but keeping the retargeting is harmless; rolling back the retargeting
and keeping the default **re-opens the silent channel**.

---

### BLOCK 5 — Make `ON_MODERATION` a durable state

| | |
|---|---|
| **Findings owned** | `AD-008` |
| **`depends_on`** | **BLOCK 4 (hard)** · **BLOCK 3 (hard — the approval path must exist for the state to be worth having)** |
| **Priority** | P0 |
| **Readiness** | **OWNER-GATED (Q2) — block does not start** |

**Ships regardless of Q2: nothing from this block.** BLOCK 5 does not start without an owner
answer. What *does* ship is its two hard prerequisites — **BLOCK 3** (the widen, correct under
all three answers) and **BLOCK 4** (the suite that can actually validate durability). That is a
strict improvement over the audit baseline, with `AD-008` recorded as **open — deferred**.

**Waits for Q2:** everything. The block writes no code, creates no migration, and adds no test
until the owner answers.

**Corrections absorbed** (§1): **R-5** — `03-DB-004` landed, so `submit_ad` **can now raise
`OperationalError`** (a fifth non-success cause). This does not change the gate, but the block's
design must place that boundary correctly: the handler layer owns it.

**Agent roster** (applies once the gate opens).
- **Implementor — yes.** Exactly one at a time.
- **Auditor — yes.** Must re-derive **both** production writers of `ON_MODERATION` at the anchor
  and prove there is **no third**, and confirm no other query filters the state in a way the
  change would alter.
- **Researcher — yes.** The one block that changes a **transaction boundary around a
  business-critical write**. The durability options have real distributed-systems consequences
  (a committed-but-never-moderated ad; a lost verdict on crash) and more than one defensible
  design exists.
- **Planner — yes.** Transaction-boundary redesign, cross-app consumer review, a large
  test-migration contract, and a decision that changes what four documents promise.
- **Validator — yes.** Highest consequence after BLOCK 6. The failure mode is **subtle**: an ad
  can become durably `ON_MODERATION` and then **never leave** that state — invisible to a seller,
  invisible to a queue that does not filter it, reaped by nothing. **Nothing in the existing
  suite can see that.**

**Decision gate — Q2. OPEN. Not decided here.** Options restated in full at §2 Q2; the
implementation shape of each:

| Option | Shape | Consequence |
|---|---|---|
| **(i)** | Commit `ON_MODERATION`, run `auto_moderate` **outside** the write transaction — a second transaction, or asynchronously | The state becomes observable; the queue, the priority service, `get_pending_queue_size` and the dashboard bucket all become real; BLOCK 3's path becomes genuinely populated; four documents become true. **Introduces a window** in which an ad is durably pending and nothing moderates it. **The recovery mechanism is part of the option, not an afterthought** — a new scheduler surface |
| **(ii)** | Commit `ON_MODERATION` and run `auto_moderate` in the **same** transaction anyway | **Fixes nothing.** The transaction still never ends with the ad in `ON_MODERATION`, so the state is never observed. Listed only so the owner can rule it out explicitly |
| **(iii)** | Drop `ON_MODERATION` from the durable set; delete the queue UI, the priority queue, `get_pending_queue_size`, and the US-A12 / US-A13 / `db-enums.md` / decision-Q commitments | **A scope explosion, not a patch.** It deletes a moderation queue four documents promise the business bought, and it changes user stories. The report warns this branch *"deletes the queue the business asked for"*. **C-7: option (iii) must not be actioned before `VAL-003` is fixed.** If chosen, the block grows by the whole deletion surface |

**File surface (semantic units).**
- `src/backend/apps/ads/services/submission.py` → `submit_ad` (the `ON_MODERATION` transition,
  the `auto_moderate` call, and the **stale comment**); `SubmitAdInput` (read).
- `src/backend/apps/ads/views/edit.py` → `ad_reactivate` (the same pair).
- `src/backend/apps/moderation/services/auto_moderation.py` → `auto_moderate`, `_pass_moderation`,
  `_fail_moderation` — **read only** unless the design requires a boundary change, which must
  then be recorded in the commit message.
- Consumers — **read and confirm, change only if forced**:
  `apps/analytics/services/moderation_analytics.py::get_pending_queue_size`;
  `PriorityService.get_queued_ads` / `get_priority_counts`; `apps/moderation/views/queue.py`;
  `AdAdmin.changelist_view`'s `moderation_queues` preset.
- `src/backend/templates/ads/dashboard.html` → the "On Moderation" bucket.
- `src/backend/apps/ads/tests/test_submission.py` → the two named cases below.
- Docs: `docs/02-database/db-enums.md` (**verify**, not necessarily edit); and **only** under
  option (iii), `docs/04-user-stories/seller-stories.md` US-S2 / `admin-stories.md` US-A12 /
  US-A13. **Never** `docs/01-spec/technical-specification.md`.

**Constraints.**
1. **Exactly two production writers**, both confirmed: `submit_ad` and `ad_reactivate`. Both call
   `transition_to(ON_MODERATION)` then `auto_moderate()` **in the same `atomic()`**.
   **`submit_ad`'s own comment is wrong under option (i)** — it states *"If `auto_moderate`
   raises, the entire `submit_ad` transaction rolls back — the ad stays DRAFT (not committed in
   ON_MODERATION)"* — and **rewriting that comment is a named deliverable of this block**.
2. **Q7 is a hard prerequisite to option (i).** `_pass_moderation`'s bare `except Exception`
   calls `_fail_moderation`. Today that failure is caught **inside the same transaction**, so the
   content verdict is at least consistent with the ad's state. Under option (i) the same handler
   would mark an ad failed for a **system** error, in a **second** transaction, with **no
   compensation**. **Q7 must be answered before option (i) ships.** This is the one place BLOCK 5
   and BLOCK 12 genuinely interact.
3. **`03-DB-004`'s `OperationalError` boundary (R-5).** `ad_edit` and `process_preview` catch it
   at the **handler** layer. `submit_ad` may raise it. Under option (i) — which is exactly the
   change that makes `submit_ad` span two transactions — this becomes reachable on the new path.
   **The design must state where the boundary sits**; the handler layer already owns it, so the
   service must not absorb it into a business outcome.
4. **`auto_moderate`'s internal `atomic()` blocks are currently savepoints**, nested inside
   `submit_ad`'s outer block. **Option (i) changes that nesting depth**, which interacts with
   phase 03's `03-DB-002` `record_event` savepoint work (`549c58e`). Phase 03 BLOCK 3 must be
   re-read.
5. **`max_ads_per_user` is the business invariant most at risk.** `set_published` is the
   authoritative guard and takes a `User.objects.select_for_update()` row lock. Under option (i),
   N ads of one seller can be pending simultaneously and the guard is evaluated N times in N
   separate transactions. The design must state whether the cap is checked at submit time (as
   now) or at publish time (as the guard is written), and **what happens to the surplus**.
6. **Visibility.** A durably-`ON_MODERATION` ad must stay out of the public queryset.
   `ListingsQuery.build_queryset` filters `status=PUBLISHED`, so this holds by construction —
   **verify it, do not assume it**, because the block is making the state real for the first time.
7. **The seller dashboard bucket is the seller-visible half.** A seller can see "On Moderation"
   for the first time. **Check the template's empty-state copy and Edit affordance**; any new
   string is an i18n obligation (`ru` **and** `bs` non-empty).
8. **Four documents promise the state** — US-S2, US-A12, US-A13, `db-enums.md` (*"awaiting
   auto-check (hidden)"*) and decision Q. Under option (i) they become true; under (iii) they must
   all be edited.

**Tests required.**
- *Must be **rewritten**:* `test_submission.py::test_submit_ad_rolls_back_when_auto_moderate_raises`
  — under option (i) the **name becomes wrong** (the ad is no longer rolled back to `DRAFT`; it
  stays `ON_MODERATION` and is retried). **Rewrite, do not delete**, and record why in the commit
  message.
- *Must be added:* an ad durably `ON_MODERATION` **between** the two transactions, observed from
  a **separate connection** — the only way to prove durability is a test that cannot see the
  uncommitted row.
- *Must be added:* the ad is **absent** from `ListingsQuery.build_queryset` while pending.
- *Must be added:* a crash/exception in the moderating step leaves the ad **recoverable** —
  retried or swept, per the chosen option. **Without this test option (i) is not shippable.**
- *Must be added:* `get_pending_queue_size()` returns the real number for the first time.
- *Must be added:* the `max_ads_per_user` interaction (constraint 5), per the chosen design.
- *Must keep passing unchanged:* BLOCK 4's retargeted tests; BLOCK 3's end-to-end approval tests
  (they are the direct consumer of the newly real state); `test_ad_lifecycle.py`;
  `test_transition_concurrency.py`.

**Docker gate command.**
```
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```
No `test-recreate` — no schema change. But the **full** fast suite is required: durability is a
whole-suite property.

**Risk / rollback.** *(data integrity)* an ad is committed `ON_MODERATION` and the moderating
step never runs — invisible to the seller, filtered out of every consumer, reaped by nothing
(mitigation: the recovery mechanism is part of the option; the recovery test is mandatory).
*(business invariant)* `max_ads_per_user` bypassed by concurrent pending ads (mitigation:
constraint 5's test). *(false confidence)* a green suite that never tested durability because
BLOCK 4 was skipped (mitigation: the hard `4 → 5` edge). *(Q7)* a system error becomes a content
verdict across a transaction boundary (mitigation: Q7 answered before (i) ships).
**Rollback: the hardest in the plan.** Reverting the code while a real queue exists re-creates
the "committed `ON_MODERATION`, nothing moderates it" state. **The block must write the
one-off query that re-drives or fails any ad sitting in `ON_MODERATION` at revert time, before
shipping.**

---

### BLOCK 6 — One sanctioned write path for ad lifecycle state in the admin

| | |
|---|---|
| **Findings owned** | `AD-001` (+ `VAL-006`, which routes through Q1) |
| **`depends_on`** | **BLOCK 3 (hard)** · **BLOCK 1 (hard — the matrix must be a named value)** |
| **Priority** | P0 — the CRITICAL, and the last of the moderation chain |
| **Readiness** | **OWNER-GATED (Q1) — DEGRADED: the unconditional half ships without the gate** |

**This block is split in two, and the split is the point.**

**SHIPS NOW — independent of Q1, in separate commits:**

| # | Unconditional violation | Why it is not a choice |
|---|---|---|
| 1 | **No `ModeratorActionLog` row** for an admin-form status change | US-A3 requires moderation actions to be logged; the form writes **zero**. US-A13's moderator-performance metric reads `published_by`/`moderated_by`, so the action is invisible to reporting. The hole was proved **by contrast** (the service path writes 1, the form path 0) |
| 2 | **`original_published_at` is mutable through the form** | `db-schema.md` and the model's own `help_text` both declare it **IMMUTABLE, audit only**; decision J says it does not drive any sweep. The form lets anyone rewrite it |
| 3 | **Silent owner transfer** — `user` is editable | One save moves the ad, its analytics and its `AdFavorite` rows to another account. **No story authorises changing an ad's owner** — US-A3's *"ban all of a user's ads"* presumes the ad set, not a reassignment |
| 4 | **Two hard HTTP 500s** — `readonly_fields` omits `rejected_at` and `moderation_failed_at` | A form save selecting `REJECTED` or `ON_MODERATION_FAILED` raises an uncaught `CheckViolation` from the `CheckConstraint` instead of a validation message. **The constraints do fire — they fire too late** |
| 5 | **The four `search_vector*` form fields** | The `ads_search_vector_update` trigger rewrites the column on every insert/update, so a manual edit is silently discarded. *"A form field that silently discards input is a future trap."* Independent of Q1; safe because the trigger neutralises manual edits |

**Violation 4 is the one case that can be fully tested and shipped without Q1** — it is not a
status-change question at all.

**WAITS FOR Q1:** whether `AdAdmin.status` becomes read-only, and through which seam the
sanctioned write happens. The options are restated at §2 Q1 and in the source plan's gate table;
**this execution does not choose.** The read-only change lands **last**, and only under an
answered option.

**Corrections absorbed** (§1): **C-20 / R-4** — `test_admin_change_form.py` (landed `a19a0ee`) is
the in-repo admin-view test precedent the source plan says does not exist; **copy it, do not
invent a harness**. `test_admin_pii_containment.py` is the introspection alternative and joins
the keep-green list. **R-13 / C-21** — `TestModerationReviewLocking` is not on this block's edit
surface but must stay green (it is BLOCK 3's). **Correction 8** — `ModeratorActionLog` has **no
moderator column**: `log_manual_publish(ad_id, moderator_id)` persists nothing of `moderator_id`.
**File it separately; add no migration here.** **Correction 7** — `_pass_moderation` writes
**two** `AnalyticsEvent`s; `set_published` writes **zero**. **R-20** — `a19a0ee` deliberately left
`has_change_permission` byte-identical and recorded phase 15 as its owner; **do not touch the
permission predicate.** **Correction 2** — `ModeratorActionType` has **five** members.

**Agent roster.**
- **Implementor — yes.** Exactly one at a time; **separate commits** so a rollback of the
  read-only change does not take violations 1–5 with it.
- **Auditor — yes.** Must introspect the **live** `AdAdmin` form at the anchor (not the source)
  and record the exact editable field set, and re-derive **every** `Ad` write path in the admin
  tier — including `changelist_view`'s `moderation_queues` preset and the four `action_*`
  buttons — so the sanctioned path is not one of several.
- **Researcher — yes.** Q1 is an architecture question with three defensible answers and
  different blast radii. The report's own CRITICAL table says *"a patch is insufficient"*.
- **Planner — yes.** New business logic must not land in a `ModelAdmin` method body (project
  rule 3), so this block almost certainly needs a service — a design with a transaction
  boundary, a permission check and an audit row.
- **Validator — yes.** The **only CRITICAL in the phase.** It changes an **authorization
  surface** and an **audit trail**. A wrong answer either removes a capability operators rely on
  or leaves the unlogged write in place.

**Decision gate — Q8. MECHANISM CLOSED by the source plan §0.6.1. Recorded, not re-opened.**

> **Closed decision (mechanism only — Q1 itself stays open).**
> `Ad.transition_to` **returns its source `AdStatus`**; `AdAdmin.save_model` triggers on
> `"status" in form.changed_data`; the audit row **reuses** `moderation_log.set_published` →
> `log_manual_publish` with `action_type=ModeratorActionType.OTHER`. **When source `==` target
> (a concurrent writer already made the change), no audit row is written** — that is precisely
> what earns the return value.
>
> **Rationale.** The plan's stated cost for the return-type change (*"touches every caller"*)
> is **wrong**: all **ten** production call sites discard the return, so there are **zero**
> production edits and exactly **one** test stub to re-annotate. A `values_list("status")`
> pre-read duplicates knowledge `transition_to` already holds **and** reads before the lock;
> re-reading a fresh instance is a full-row fetch including the four `tsvector` columns.

**File surface (semantic units).**
- `src/backend/apps/ads/admin.py` → `class AdAdmin`: `readonly_fields`, the absence of
  `fields`/`fieldsets`/`exclude`/`form`, the `get_form`-level field contract, a new `save_model`
  override (**only** under the answered Q1 option), `actions` (**read**), `changelist_view`
  (**read**), `has_change_permission` / `has_view_permission` (**READ ONLY — phase 15 owns them**).
- **New (under the answered option):** a service module under
  `src/backend/apps/ads/services/` for the sanctioned admin lifecycle write, so the logic is not
  in a `ModelAdmin` method body (project rule 3). Named by the Planner. **`apps/*` must not
  import `telegram_bot/*`.** No `__init__.py` in `services/` — it is an implicit namespace
  package.
- `src/backend/apps/moderation/services/moderation_log.py` → `set_published`, `set_rejected` —
  **read only unless Q8 forces a new writer**; the audit row must go through the existing service
  so there is exactly **one** writer of `ModeratorActionLog` for a publish.
- `src/backend/apps/ads/models.py` → `Ad.transition_to` (**read only** unless Q8 option ii is
  chosen, in which case the return type changes — and per the closed decision that touches zero
  production sites).
- **New** `src/backend/apps/ads/tests/test_admin_ad_change_form.py` — a change-form test module
  following the `test_admin_change_form.py` precedent.
- `src/backend/apps/ads/tests/test_ad_lifecycle.py` → `TestOriginalPublishedAtImmutability`
  (**keep green, do not edit**).
- Docs: `docs/04-user-stories/admin-stories.md` US-A3 — **required under option (a)** to withdraw
  *"change status"*, and **required under (b)** to record that the sanctioned seam is the service.
  **Never** `technical-specification.md`.

**Constraints.**
1. **The terminal-state resurrection is the sharpest evidence.** `Ad.transition_to` refuses every
   transition out of `DELETED` with a `ValueError`, but the form never calls it — so
   `DELETED → published` is a plain `UPDATE` and returns **302**. The terminal-state rule is not
   merely bypassed, it is **inverted**.
2. **The wrong-timer consequence is the CRITICAL example, not a side effect.** A moderator sets
   `published_at` 999 days in the past; the next `archive_sweep` moves the ad straight to
   `ARCHIVED`. Far in the future: unarchivable for years. Both are operator actions with **no
   validation**.
3. **`transition_to`'s `refresh_from_db()` fights a form save.** It is the method's first
   statement, so a sanctioned path through `transition_to` discards the form's other unsaved
   field values unless the ordering is right. **The Planner must state the ordering**, and the
   Researcher must confirm whether a form save can safely route through a method that re-reads.
   The change-form tests must assert on the **whole saved row**, not one field.
4. **Under the sanctioned-service option, `save_model` must not double-write.** If the service
   path already sets `published_at` and `original_published_at`, the form must not then write
   them again from its own fields. The four `search_vector*` fields are the same class of trap.
5. **Do not fix `VAL-003` here.** The gates were widened in BLOCK 3. This block touches
   `AdAdmin`; it does **not** touch `bulk_approve` or the review views.
6. **Do not drop the four `action_*` buttons** under the sanctioned-seam option — they are the
   sanctioned seam.

**Tests required.** (New module, all demonstrated **red** first; pattern copied from
`test_admin_change_form.py`: module-local `staff_user` / `superuser` fixtures, `Client`,
`force_login`, `reverse("admin:ads_ad_change", args=[target.pk])`.)
- *Must be added* — **violation 4, ships without Q1:* a POST selecting `REJECTED` and one
  selecting `ON_MODERATION_FAILED` returns a **validation error, not an HTTP 500**.
- *Must be added* — **the `search_vector*` removal, ships without Q1:* the four `search_vector*`
  fields are **not** in the form's field list.
- *Must be added* — **violations 1–3, ships without Q1 in shape:* `original_published_at` is
  **immutable** through the form; `user` is **not** reassignable through the form; `DELETED →
  published` through the form is refused.
- *Must be added* — per the answered Q1: a staff POST of `status=published` with a hand-picked
  `published_at` either is refused, or commits **with** a `ModeratorActionLog` row and an
  `AnalyticsEvent`. **Assert the row count, not the absence of an exception.**
- *Must be added* — under the sanctioned-service option: a form status change writes exactly
  **one** `ModeratorActionLog` row and exactly **one** `AnalyticsEvent` — **not two, not zero**.
  Note correction 7: `_pass_moderation` writes **two** events; `set_published` writes zero.
  Record which this assertion counts.
- *Must keep passing unchanged:* `test_ad_lifecycle.py::TestOriginalPublishedAtImmutability`
  (both cases) and `TestPublishedAtUpdates`; `test_ad_constraints.py` in full;
  `test_transition_concurrency.py`; BLOCK 3's end-to-end approval tests; phase 04's
  `test_admin_pii_containment.py` (verify it is not affected); BLOCK 3's
  `TestModerationReviewLocking`.

**Docker gate command.**
```
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/ src/backend/apps/moderation/tests/ src/backend/apps/users/tests/test_admin_pii_containment.py src/backend/apps/users/tests/test_admin_change_form.py" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```

**Risk / rollback.** *(catastrophic)* `status` → read-only lands while BLOCK 3 has not shipped and
moderators lose the ability to publish entirely — mitigation: the hard `3 → 6` edge **and** the
read-only change lands **last**. A save routed through `transition_to` silently discards the
form's other field values (constraint 3). A double audit row or double `AnalyticsEvent`
(the "exactly one" assertions). An operator depended on owner reassignment (this is violation 3,
which is **unconditional**; if the owner disputes it, the dispute belongs to **Q1**, not to this
block — say so in the commit message). **Rollback:** the five unconditional fixes and the
read-only change are **independently revertible** — which is exactly why the block is structured
as separate commits.

---

### BLOCK 7 — Retention anchor, delete-sweep predicate, and the new partial index

| | |
|---|---|
| **Findings owned** | `AD-004`, the `VAL-005` decision |
| **`depends_on`** | BLOCK 2 (soft — same retention story; BLOCK 2 must not assume an anchor) · **BLOCK 4 (HARD — new: `conftest.py` contention, C-15)** · **BLOCK 10 (hard — `7 → 10` migration serialisation)** |
| **Priority** | P1 — the one HIGH in the phase |
| **Readiness** | **OWNER-GATED (Q4) — with an undisclosed scope multiplier (R-1 / C-15)** |

**Ships regardless of Q4:** the cosmetic `db-retention.md` fragment repair — see §2 Q4. It is
recorded and executed in **BLOCK 14** (documentation-only), because that is where the
documentation-only work lives and it removes the need to start BLOCK 7 early.

**Waits for Q4:** the anchor, the predicate, and the migration. **This is the one HIGH in the
phase that cannot be partially delivered** — "correct" is undefined without the answer.

**Corrections absorbed** (§1): **C-15** — under Q4 options (i)/(ii) the **whole of
`test_sweep_delete.py` goes red** (`TestDeleteSweep`, 6 cases, plus `TestConcurrentSweep`) and
**`src/backend/conftest.py::_set_status_timestamp` must change** — BLOCK 4's reserved file. A
**new cross-block contention** the source plan does not record. Also: **C-17** — `03-DB-008`
never touched `delete_sweep`; **C-18** — `03-DB-011` already removed the `storage_keys`
pre-collection, so that "must not touch" note is **void**; **C-19** — `test_sweep_lock_structure`
now asserts `session is True and in_atomic is False` **only** for `_SESSION_SCOPED_BATCHERS =
{"archive_sweep", "recompute_normalized_prices"}`, and asserts `delete_sweep` is
**`in_atomic is True, session is False`**. Next free migration is **`0009_*`**.

**Agent roster.**
- **Implementor — yes.** Exactly one at a time.
- **Auditor — yes.** Must re-read `delete_sweep.Command.handle`, `Ad.Meta.indexes` and **all
  four** disagreeing documents at the anchor, and confirm **at runtime** that
  `GREATEST(published_at, archived_at)` is **not** directly expressible in a Django `Q` and that
  **no second query reads `archived_at`**.
- **Researcher — yes.** The only block that must choose between three query/index shapes with
  different write costs, on the hottest table in the system. The `GREATEST` branch needs two
  partial-index-friendly branches, which changes the index story again.
- **Planner — yes.** A **schema migration**, a data-meaning change, a documentation reconciliation
  across three documents, and a hard prerequisite on a new partial index.
- **Validator — yes.** The change alters **what gets permanently deleted**. A wrong anchor either
  hard-deletes a seller's archived ad far too early (**irreversible**) or keeps it forever.
  Neither failure is visible in the suite.

**Decision gate — Q4 (the anchor). OPEN. Not decided here.** Options restated at §2 Q4. The
implementation shape of each:

| Option | Predicate shape | Index consequence |
|---|---|---|
| **(i) `GREATEST(published_at, archived_at)`** — select when **both** are older than the cutoff | `Q(published_at__lt=cutoff) & Q(archived_at__lt=cutoff)`, or **two branches** | A compound two-column condition **cannot** be served by a single-column partial index. Needs a **new**, possibly two-column index |
| **(ii) `published_at` only** | Re-key the sweep on `published_at`, drop `archived_at` entirely | One new partial index `(status, published_at) WHERE status='archived'`; the old index is simply removed. **A seller who manually archives a 3-year-old ad has it hard-deleted on the next run** — real seller harm, stated to the owner as such |
| **(iii) `archived_at`, longer window** (60 d → 120 d) | **No predicate change, no index change** | This is the **documentation** option: reconcile `db-retention.md` instead of the code. Cheapest, and it leaves the "manual archive is 60 days" complaint half-answered |

**Decision gate — the index. A hard prerequisite, not an optimisation.** `IX_ads_delete_sweep` is
`(status, archived_at) WHERE status='archived'` today. **Re-keying the sweep on `published_at`
silently drops it**, and `delete_sweep` runs against the hottest table.

| Option | Change | Consequence |
|---|---|---|
| **A** | `AddIndex` the new index, `RemoveIndex` the old | Clean — one index for one predicate. Brief `ACCESS EXCLUSIVE` lock on `ads`; DDL-only, no table rewrite. `CREATE INDEX CONCURRENTLY` is **not** available inside a Django `AddIndex` — the Planner must state the lock window and whether a separate `RunSQL` concurrent step is warranted |
| **B** | Add the new index, **keep** the old one | Zero risk on the existing index, but leaves a dead index costing write amplification on every `status` change, and it will confuse the next reader of `db-indexes.md` |

**Either way `docs/02-database/db-indexes.md` is a named DOC-UPDATE** — it documents
`IX_ads_delete_sweep` today and would be wrong afterwards.

**Decision gate — which document is reconciled.** The owner's answer determines whether the
code changes or the documentation does (option (iii) is the documentation answer). **The Planner
must record, in the commit message, which document was reconciled and why**, so the next reader
does not re-open it. **Never** `technical-specification.md` — phase 06 owns it.

**Decision gate — the row lock.** `delete_sweep.Command.handle` has **no `select_for_update()`**,
unlike `archive_sweep` (which has one, with a `DB-010` comment). Adding one is a row-lock
acquisition on a queryset about to be hard-deleted. **This execution records the constraint and
does not decide it:** per **C-19**, `delete_sweep` is asserted `in_atomic is True, session is
False` in `test_sweep_lock_structure.py`, so **the block must not convert it to per-batch
commits** — that needs a session lock and would fail the assertion. Whether a row lock is added
here or deferred to phase 03 is a Planner decision recorded in the commit message either way.

**File surface (semantic units).**
- `src/backend/apps/core/management/commands/delete_sweep.py` → `Command.handle` (the cutoff,
  the filter, and possibly `select_for_update`). **The `storage_keys` pre-collection is already
  gone (C-18) — do not look for it.**
- `src/backend/apps/ads/models.py` → `Ad.Meta.indexes` → the `IX_ads_delete_sweep` entry.
- **New:** `src/backend/apps/ads/migrations/0009_<name>.py` (**number re-read immediately before
  generation**; do **not** read `__pycache__` — R-19).
- `src/backend/conftest.py` → `_set_status_timestamp` — **NEW surface for this block**, required
  only under options (i)/(ii) (C-15). Reserved per §5.
- `src/backend/apps/core/tests/test_sweep_delete.py` (whole file is the blast radius);
  `src/backend/apps/core/tests/test_sweep_lock_structure.py` (**keep green in full**).
- Docs: `docs/02-database/db-retention.md`; `docs/02-database/db-indexes.md`; the reconciled user
  story (`seller-stories.md` US-S7 and/or `admin-stories.md` US-A5, per the anchor decision).
- **Not touched:** `archive_sweep.py` (except a read to confirm the auto path);
  `technical-specification.md`.

**Constraints.**
1. **`IX_ads_archive_sweep` is already `(status, published_at) WHERE status='published'`** and
   `archive_sweep` already keys on `published_at`. The project is *already* inconsistent: the
   auto path keys on `published_at`, the manual path's downstream sweep keys on `archived_at`.
   This block makes them agree, one way or the other.
2. **The `session is False` constraint (C-19).** `delete_sweep` stays in the transaction-scoped
   group: `in_atomic is True, session is False`. **No per-batch commits.** The block adds **no new
   `AdvisoryLockId` member** (phase 05 allocates none — R-10).
3. **A back-dated manual archive is the regression test.** Assert the selection behaviour **per
   the chosen anchor**; assert the **auto** path is unaffected. The validator independently
   verified the `GREATEST` branch preserves the auto path (`archived_at − published_at = 61 days`
   resolves `GREATEST` to `archived_at`, so auto-archive still fires at `published_at + 120 d`) —
   that verification is **inherited and must be re-run**.
4. **`test_purges_manually_archived_recent_publish` is a shipped green test whose docstring pins
   the current anchor.** Under options (i)/(ii) it changes meaning and **must be rewritten with
   the reason recorded** (project rule 2), not deleted.
5. **Migration number is re-read immediately before generation** (§1). **Two migrations with the
   same number in one app is a hard failure, not a merge conflict.**
6. **Hardcoding constraint, confirmed:** `db-retention.md` states *"All retention values are
   hardcoded in the respective management command source files. No environment variables or CLI
   arguments (beyond `--dry-run`) are read for retention durations."* No env-var indirection.

**Tests required.**
- *Must be **rewritten**:* `test_purges_manually_archived_recent_publish` (options (i)/(ii)) —
  the docstring currently pins `archived_at`.
- *Must be added:* a **manual** archive back-dated 61 days is selected / not selected **per the
  chosen anchor** — demonstrated **red** against the pre-fix code.
- *Must be added:* the **auto** path is unaffected — an ad whose `archived_at` is 61 days old but
  whose `published_at` is 119 days old is **not** deleted before `published_at + 120 d`.
- *Must be added:* a long-lived archived ad (archived long after publication) is **still
  eventually deleted** — the chosen anchor did not create a permanent-archive hole.
- *Must be added:* a `delete_sweep --dry-run` case confirming the count and that **nothing is
  written**.
- *Must keep passing unchanged:* `test_dry_run_does_not_delete` and every other case in
  `test_sweep_delete.py`; **`test_sweep_lock_structure.py` in full** (including the name-set
  equality assertion — this block adds **no** lock-taking command).
- *Must stay green under (i)/(ii):* **all of `test_sweep_delete.py`**, via the
  `_set_status_timestamp` change (C-15).

**Docker gate command.**
```
.\Makefile.ps1 test-recreate
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/ src/backend/apps/ads/tests/" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```
`test-recreate` is **required** — a new `ads/0009_*` migration.

**Risk / rollback.** *(irreversible data loss)* the chosen anchor deletes a seller's archived ad
earlier than the user stories promise (mitigation: the auto-path test; the owner's explicit
answer; the commit message records the answer). The new partial index is omitted and the sweep
degrades to a sequential scan on the hottest table. `0009_*` collides (mitigation: re-read
immediately before generating — **the most likely process failure in the block**). The migration
takes a lock on `ads` long enough to stall the bot (the DDL is index-only, not a table rewrite).
**`conftest.py` is edited on a stale read** (C-15 — reserve per §5, re-read immediately before,
explicit paths). **Rollback:** the migration reverses (`RemoveIndex` of the new, `AddIndex` of
the old). **Rolling back the predicate while keeping the index is harmless; rolling back the
predicate and keeping the new index leaves a dead index. Revert all three or none.**

---

### BLOCK 8 — Editing a failed ad must not be a dead end

| | |
|---|---|
| **Findings owned** | `AD-002` |
| **`depends_on`** | **BLOCK 1 (hard — the matrix must be a named value before an edge can be added)** |
| **Priority** | P1 |
| **Readiness** | **OWNER-GATED (Q5) — DEGRADED: BLOCK 8A ships without the gate** |

**BLOCK 8A — SHIPS NOW, independent of Q5.** Replace the `else:` catch-all with an **explicit
status allow-list**. The validator's instruction is explicit: *"The fix should gate the branch on
an explicit status allow-list rather than adding one more branch."* **Adding a sixth branch is
forbidden.** This is a pure structural fix — it changes **no product rule**, only the
enumeration, and it makes the branch's behaviour **defined** for all seven statuses. Every status
outside the list gets an explicit, tested refusal instead of a silent write.

**BLOCK 8B — WAITS FOR Q5.** The product rule: re-moderate, refuse, or hide the affordance; the
purge-timer interaction; the dashboard link gating. Options restated at §2 Q5.

**Corrections absorbed** (§1) and from the code context: the catch-all is reached by **five** of
the seven statuses — `DRAFT`, `ON_MODERATION`, `ON_MODERATION_FAILED`, `REJECTED`, `DELETED` —
**and** by `ARCHIVED` when the POST carries no `reactivate`. `ALLOWED_TRANSITIONS[ON_MODERATION_FAILED]
= {REJECTED}` — the only legal target — so option (b) **must add the edge deliberately**.
`moderation_failed_at` is **not** in the `update_fields` list, so the 7-day `purge_failed_ads`
timer (keyed on `moderation_failed_at`, per `db-retention.md` and `IX_ads_purge_failed`) is
untouched.

**Agent roster.**
- **Implementor — yes.**
- **Auditor — yes.** Must re-derive, at the anchor, the **full** set of statuses the catch-all is
  reached by (**five**, not the two the report named, plus `ARCHIVED`-without-`reactivate`) and
  confirm `dashboard.html` renders the Edit link **unconditionally**. Both corrections are
  load-bearing for the allow-list's size.
- **Researcher — yes.** Q5 has three options with materially different product behaviour, and the
  code context points out that **only one** actually resets the purge timer.
- **Planner — yes.** The fix spans a view, a state-machine edge and a template, and it
  **rewrites a shipped green test**. It must also decide where the "you cannot edit this"
  affordance lives — a UX question the report only partly answers.
- **Validator — yes.** HIGH severity, and the failure mode is **a seller losing work**: the
  current behaviour accepts the edit, tells them nothing, and the purge later reclaims the ad.

**Decision gate — Q5. OPEN. Not decided here.** Options restated at §2 Q5; implementation shape:

| Option | Shape | Consequence |
|---|---|---|
| **(a)** | Allow-list the direct-save branch to exactly `DRAFT` and `ON_MODERATION`; a clear error for everything else | Smallest and most conservative. **Does not fix the dead end — it hides it.** `moderation_failed_at` is still not reset, so the ad is still unrecoverable. The seller is told, which is better |
| **(b)** | Add `ON_MODERATION_FAILED → ON_MODERATION` to the matrix and route through `submit_ad` so the ad is re-moderated and `moderation_failed_at` is reset | **The only option that actually resets the purge timer**, and it is where `VAL-006` says the logic should live — one write path, one place. But it is **a deliberate loosening of a rule the state machine enforces on purpose**, and **retry bounding is part of the option** or a seller can reset the 7-day timer forever |
| **(c)** | Stop advertising the edit for statuses where it cannot succeed | Pure UI. **Leaves the defect in place for any caller who POSTs directly** — security-by-hiding. Weak on its own |

**File surface (semantic units).**
- `src/backend/apps/ads/views/edit.py` → `ad_edit` (the `else:` catch-all branch and its
  `update_fields` list; under option (b) also the route into `submit_ad`).
- `src/backend/apps/ads/models.py` → module-level `ALLOWED_TRANSITIONS` (**only** the
  `ON_MODERATION_FAILED` entry, and **only** under option (b)).
- `src/backend/apps/ads/services/submission.py` → `submit_ad` (**read only**, unless the retry
  bounding lands there).
- `src/backend/apps/ads/tests/test_edit.py` → `class TestEditOtherStatusDirectSave`
  (**rewrite**); `class TestPublishedTextEdit` (**DO NOT TOUCH** — BLOCK 2's).
- `src/backend/templates/ads/dashboard.html` → the unconditional Edit link.
- `src/backend/apps/ads/tests/test_submission.py` → **read**; must stay green.
- Docs: `docs/04-user-stories/seller-stories.md` (only if the owner's answer changes the
  promise). **Never** `technical-specification.md`.

**Constraints.**
1. **A shipped green test asserts the catch-all and must change (project rule 2).**
   `TestEditOtherStatusDirectSave::test_edit_on_moderation_direct_save` — its docstring claims
   coverage of `ON_MODERATION` **and** `ON_MODERATION_FAILED` but only one test exists, and it
   asserts `ad.status == AdStatus.ON_MODERATION  # unchanged`. **Any allow-list or re-moderation
   fix breaks it.** Rewrite the assertion **and** the misleading class docstring, with the reason
   recorded, so the next reader does not trust it.
2. **The defect's mechanism is the `update_fields` list.** The catch-all writes
   `["title", "description", "price_amount", "price_currency", "price_normalized_eur",
   "updated_at"]` — **neither `status` nor `moderation_failed_at` is present**. So the 7-day purge
   timer is not reset and the rewritten content is reclaimed by the purge. Statically derivable;
   the block confirms it at runtime.
3. **"Just call the driver" is not available today.** Under option (b) the block **adds the
   edge**; under (a)/(c) it does not, and the allow-list is what stops `submit_ad` being called
   on a refused transition.
4. **The template is part of the fix, not decoration.** Under option (c) it is the whole change;
   under (a)/(b) the link should be gated on the statuses where edit can succeed, or the seller
   still clicks into a dead end. **Any new or moved string is an i18n obligation** (`ru` and `bs`
   non-empty).
5. **The view already owns one `atomic()` + `select_for_update()`.** Routing through `submit_ad`
   means a **nested** call inside that block, and `submit_ad` opens its own `atomic()` and
   re-fetches with `select_for_update()`. The Researcher must state the nesting depth and whether
   the re-fetch discards the form's pending values — the same interaction BLOCK 6 constraint 3
   raises from the other direction.
6. **Do not touch the reactivation and text branches.** They already call `submit_ad` and render
   `errors[0]`. Their tests must stay green unchanged.
7. **`VAL-006` constraint.** If Q1 lands a single sanctioned write path (BLOCK 6), this fix has
   **exactly one place to live** and must be written there. If BLOCK 6 has not landed, this block
   writes the edge and the view branch and BLOCK 6 must adopt them. **Record which, in the commit
   message.**

**Tests required.**
- *Must be **rewritten**:* `TestEditOtherStatusDirectSave::test_edit_on_moderation_direct_save` —
  assertion and class docstring, with a comment recording that the test encoded the defect.
- *Must be added* (**BLOCK 8A, ships without Q5**): a test enumerating **each** of `DRAFT`,
  `ON_MODERATION`, `ON_MODERATION_FAILED`, `REJECTED`, `DELETED` **and the
  `ARCHIVED`-without-`reactivate` case**, asserting the *defined* outcome for each. This is the
  structural fix's guard — a future `else:` re-broadening fails it.
- *Must be added* (**8A**): a POST to an ad in a non-allow-listed status is **refused** with an
  actionable message and the ad is **unchanged** — demonstrated **red** before the fix.
- *Must be added* (**8B**, options (a)/(c)): the dashboard Edit link is present **exactly** for
  the statuses where edit can succeed.
- *Must be added* (**8B**, option (b) — **the only test that proves the finding is fixed rather
  than hidden**): editing a failed ad **re-moderates** it; `moderation_failed_at` is reset; the
  status leaves `ON_MODERATION_FAILED`; `purge_failed_ads` does **not** reclaim the rewritten
  content. Plus the **retry bounding** — repeated failed resubmissions do not extend the ad's
  life **indefinitely**.
- *Must keep passing unchanged:* `TestPublishedTextEdit` in full (BLOCK 2's);
  `test_submission.py` in full; `test_ad_lifecycle.py`; `test_i18n_completeness.py`;
  `test_i18n_pipeline.py`.

**Docker gate command.**
```
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```

**Risk / rollback.** *(seller data loss, the finding itself)* options (a)/(c) ship and the ad is
still purged, only now with a message — mitigation: the gate table states that "must not reset
`moderation_failed_at`" is **not** a fix, and the commit message must state **which consequence
was accepted**. A wrong fix blocks a legitimate edit (mitigation: the five-status enumeration
test). A future `else:` re-broadening silently returns (mitigation: the same enumeration test).
**Rollback:** 8A and 8B are separate commits; reverting 8B leaves the branch defined for all
seven statuses, which is an improvement over the catch-all.

---

### BLOCK 9 — The bulk-moderation endpoint needs a transaction, a lock and honest errors

| | |
|---|---|
| **Findings owned** | `AD-010` |
| **`depends_on`** | — |
| **Priority** | P1 |
| **Readiness** | **READY-WITH-CORRECTIONS** |

**Endpoint shape confirmed intact at the anchor:** no `atomic()`, no `select_for_update()`, a
bare `except Exception`, a `StrEnum` identity comparison, `MAX_BULK_ACTIONS = 100`, service
delegation, and no `ban` branch.

**Corrections absorbed** (§1): **C-16 / R-12** — the tripwire is in
`apps/moderation/tests/test_admin_actions.py` and is **phase 03's** (`DB-003`), not phase 04's
and not in `apps/users/tests/`. **Correction 6** — the endpoint's own tests are **one** class,
`test_priority_service.py::TestBulkModerationActionView` (**22** methods) — there is no separate
bulk-endpoint test module. **C-6** — `api_bulk.py` imports `approve_ad`, `reject_ad` from
`apps.moderation.admin_actions`, and `bulk_approve(queryset, moderator_id)` takes a **QuerySet**,
so the source plan's *"call `bulk_approve`"* instruction is **unexecutable**.

**Agent roster.**
- **Implementor — yes.** Exactly one at a time.
- **Auditor — yes.** Must re-derive the endpoint's full failure surface and the service function
  signatures it delegates to, and confirm the response contract with its (single) test class.
- **Researcher — no.** Q11 is **closed** (below); the six failure classes are decided. Nothing
  remains to research.
- **Planner — no.** The transaction shape, the failure taxonomy and the response contract are all
  specified. What remains is execution.
- **Validator — yes.** The endpoint changes the **locking discipline** of a moderator write path
  and the **shape of a public response**. An independent review must confirm the six classes map
  onto real code paths and that no path silently returns success.

**Decision gate — Q11. CLOSED by the source plan §0.6.1. Recorded, not re-opened.**

> **Closed decision.** Per-ad `atomic()` + `select_for_update()`, iterating **`sorted(ad_ids)`**
> (pk order, matching `bulk_approve`'s documented rationale). Six failure classes. Response shape
> `{"completed": N, "errors": [...]}` and **HTTP 200 unchanged**; `reject_ad` returns `bool` so
> `completed` is honest.
>
> **Rationale.** A per-request `atomic()` is **unexecutable** as the loop stands: the view catches
> the exception inside the `with`, the transaction is already `needs_rollback`, and the next
> iteration's `Ad.objects.get` raises `TransactionManagementError` → 500. It would only work with
> a savepoint per iteration, which **is** per-ad `atomic()`. A bulk `QuerySet` rewrite changes the
> endpoint's semantics from *"these ids"* to *"this queryset"* — overreach for MEDIUM. An
> `advisory_lock` is the wrong tool: advisory locks are the **scheduled-job idempotency**
> mechanism, row locks are the **web-request** primitive.
>
> **Shape to mirror:** `apps/moderation/views/review.py`'s `approve_ad` view **already** has the
> per-ad `atomic()` + `select_for_update()` pattern this decision selects. Copy it.

**File surface (semantic units).**
- The bulk moderation endpoint view → the request handler, its `atomic()`/lock usage, the
  `MAX_BULK_ACTIONS` check, the `StrEnum` comparison, and the error-collection loop.
- `src/backend/apps/moderation/admin_actions.py` → `approve_ad`, `reject_ad` (**read only** —
  the endpoint delegates; do not change their contracts here).
- `src/backend/apps/moderation/tests/test_priority_service.py` →
  `class TestBulkModerationActionView`.
- `src/backend/apps/moderation/tests/test_admin_actions.py` →
  `class TestBulkLockingStructure` — **keep unchanged**; it is the tripwire (C-16).

**Constraints.**
1. **The response contract does not change.** `{"completed": N, "errors": [...]}` and HTTP 200.
   A client parsing that body must not break.
2. **`completed` must be honest.** It counts ads that actually reached the target status, not ads
   attempted.
3. **The bulk-ban tripwire binds (C-16): `bulk_ban_users` must not gain
   `select_for_update`.** This block touches the **JSON endpoint**, not the admin actions.
4. **Six failure classes** — each must map to a real code path, not a branch that cannot occur.
5. **No `print()`**; all failures via `logger`.

**Tests required.**
- *Must be added:* each of the six failure classes asserted through the endpoint, with the
  response body's `completed` count and the specific `errors` entry — **not** the absence of an
  exception.
- *Must be added:* a test that a partial success reports `completed` as the number that
  **succeeded** and an error per failure.
- *Must be added:* the `StrEnum` identity comparison is exercised by a value loaded fresh from the
  database, so the comparison cannot pass by object identity luck.
- *Must keep passing unchanged:* `class TestBulkModerationActionView` in full (22 methods) except
  where a response assertion must change;
  `TestBulkLockingStructure::test_bulk_ban_users_not_locked` (phase 03's tripwire).

**Docker gate command.**
```
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/moderation/tests/ src/backend/apps/ads/tests/" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```

**Risk / rollback.** A partial failure is reported as success (mitigation: the honest-`completed`
test). A deadlock because two concurrent bulk requests take overlapping rows in different orders —
mitigation: **iterating `sorted(ad_ids)`** is the closed decision's deadlock-avoidance mechanism;
do not iterate request order. **Rollback:** one commit, no migration; revert restores the previous
unlocked behaviour.

---

### BLOCK 10 — `AdImage.position` needs a uniqueness constraint

| | |
|---|---|
| **Findings owned** | `AD-014` |
| **`depends_on`** | **BLOCK 7 (hard — `7 → 10` migration-number serialisation)** |
| **Priority** | P2 |
| **Readiness** | **READY-WITH-CORRECTIONS** |

**Model state confirmed:** `AdImage.Meta` has four `CheckConstraint`s, four single-column indexes
and **no** `(ad, position)` constraint; `position` is `default=0`;
`test_copy_ad_image_positions_preserved` uses `[0, 2, 5]` — the contiguity guard, **present and
unchanged**.

**Corrections absorbed** (§1): the next free `apps/ads` migration is **`0009_*`** — **BLOCK 7
claims it**, so the `7 → 10` serialisation still binds. And the pre-flight is **one query against
the test DB plus a recorded static argument** — **do not re-escalate to production-shaped data**,
and a green `test-recreate` is **not** evidence (R-18).

**Agent roster.**
- **Implementor — yes.**
- **Auditor — yes.** Runs the **one** pre-flight query and records it **verbatim**.
- **Researcher — no.** Q9-sizing is closed.
- **Planner — no.** The constraint shape is specified: uniqueness only.
- **Validator — yes.** It is a schema migration on a table with concurrent writers; an
  independent review must confirm the constraint covers exactly the intended pair and that no
  existing test encodes contiguity.

**Decision gate — Q9-sizing. CLOSED by the source plan §0.6.1. Recorded, not re-opened.**

> **Closed decision.** Ship the `UniqueConstraint`; the pre-flight is scaled to **one** query.
>
> **Rationale.** The argument is **not** *"duplicates exist today"* — it is that `position` has
> `default=0` and every direct writer can collide, so the constraint converts silent gallery
> corruption into a loud `IntegrityError`. Every sibling relation already carries a named
> `UniqueConstraint`; `ad_images` without one is the anomaly. The plan's escalation to
> *"production-shaped data as a hard gate"* is disproportionate **and unmeetable inside the
> command contract** — the containerised `test` service is the only sanctioned DB access, and a
> `--create-db` run is explicitly **not** representative.

**File surface (semantic units).**
- `src/backend/apps/ads/models.py` → `AdImage.Meta.constraints` (the new
  `UniqueConstraint(fields=["ad", "position"], name=…)`).
- **New:** `src/backend/apps/ads/migrations/0010_<name>.py` — **re-read the directory immediately
  before generation; the number is contested** (§1; **do not read `__pycache__`**, R-19).
- `src/backend/apps/ads/tests/test_ad_constraints.py` → `class AdImageConstraints` (or the
  existing constraint class) — the constraint's own guard.

**Constraints.**
1. **The constraint is uniqueness-only. Contiguity is FORBIDDEN.** No `CheckConstraint` requiring
   `position >= 0` and no gap-free requirement — `copy_ad` legitimately produces `[0, 2, 5]` and
   `test_copy_ad_image_positions_preserved` pins it.
2. **Use `validate_default=False`** if and only if the static argument shows a collision; do not
   add `Deferrable`.
3. **The static production-reachability argument** is recorded beside the query in the commit
   message: `position` has `default=0`, and there are at least two direct writers
   (`AdImageService.create_or_skip(**extra)` and `copy_ad`).
4. **Migration number discipline** — `7 → 10` is serial (§4).

**Tests required.**
- *Must be added:* a case asserting the database **rejects** two `AdImage` rows on the same
  `(ad, position)` — an `IntegrityError`, not a silent second row.
- *Must keep passing unchanged:* `test_copy_ad_image_positions_preserved` (`[0, 2, 5]`) — the
  contiguity guard, **untouched**; the existing `AdImage` `CheckConstraint` cases;
  `test_ad_image_service.py` in full (it has an `isolated_media_root` fixture).

**Docker gate command.**
```
.\Makefile.ps1 test-recreate
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```
`test-recreate` is **required** — a new `ads` migration.

**Risk / rollback.** An existing test row set collides and the migration fails (mitigation: the
pre-flight query, recorded verbatim, plus the static argument). The constraint is over-tightened
into a contiguity rule and `copy_ad` breaks (mitigation: constraint 1; the `[0, 2, 5]` guard).
The migration number collides with BLOCK 7's (mitigation: §4's serialisation; re-read the
directory). **Rollback:** `RemoveConstraint` reverses cleanly.

---

### BLOCK 11 — `ad_copy` must not render a raw driver error into a seller's chat

| | |
|---|---|
| **Findings owned** | `AD-012` (bot half **and** DB half) |
| **`depends_on`** | — |
| **Priority** | was P2 as a live code block; now **record-only** |
| **Readiness** | **MOOT-SUPERSEDED — a duplicate-patch hazard (R-3, R-17)** |

**`AD-012` IS ALREADY FIXED. BOTH HALVES. `BLOCK 11` AS WRITTEN MUST NOT BE EXECUTED.**

| Half | Shipped by | Evidence |
|---|---|---|
| **Bot half (CWE-209)** | **`ba1b059`** | `ad_copy.py` renders `_("Failed to copy ad.")` with `logger.exception(...)` retained; the msgid is present in `ru` (non-empty), `bs` and `en`; `test_copy_unexpected_error_hides_driver_text` is shipped |
| **DB half** | **`ba1b059`** | `copy_ad` deletes the seller's `DRAFT` inside the open `atomic()`, wraps the create in a savepoint with `try` outside, `except IntegrityError:` cleanup-and-retry once; `_build_ad_copy()` helper; the docstring carries the policy and the savepoint rationale; `test_copy_ad_replaces_existing_draft` is shipped |

**An Implementor who executes BLOCK 11 as written ships a second patch for one predicate** —
exactly the hazard `VAL-004`/`C-4` were raised to prevent. **This is a process failure with a
HIGH severity, not a code risk.**

**Disposition — what actually happens to this block.**
1. **No Implementor, no commit, no tests.** BLOCK 11 is recorded as **superseded**, with
   `ba1b059` as the evidence.
2. The **residual** — *all non-permission failures collapse into one generic string* (ad-not-found
   vs a non-`PermissionError` permission failure vs anything else) — is a **different, smaller**
   job than BLOCK 11 describes. It is **not** in the source plan's block set.
   **This execution records it and does not execute it.** Building it here would be speculative
   scope creep; silently dropping it would lose the record.
3. **Agent roster — all four specialised agents are NOT required, and the Implementor is NOT
   required.** Implementor: nothing to implement. Auditor: only to confirm `ba1b059` is still in
   the tree (cheap, do it once). Researcher / Planner / Validator: **no** — there is no approach
   to choose, no design, and no change to review.

**File surface: none.** Recording only. The record lives in BLOCK 14 and in the final report.

**Tests required: none.** `test_copy_unexpected_error_hides_driver_text` and
`test_copy_ad_replaces_existing_draft` must **keep passing unchanged** — that is the assertion
that the shipped state is still shipped.

**Docker gate command:** none specific. The general gate
(`$dc run --rm --env PYTEST_SKIP_MARKERS=seed test`) covers it. The bot ad-copy tests are
`src/telegram_bot/tests/`.

**Risk / rollback:** the only risk is **shipping the duplicate patch**. Mitigation: this record.
**Rollback: not applicable — nothing is shipped.**

---

### BLOCK 12 — An expired draft is not a moderation failure

| | |
|---|---|
| **Findings owned** | `AD-016` |
| **`depends_on`** | — |
| **Priority** | P1 |
| **Readiness** | **READY-WITH-CORRECTIONS** |

**The defect is narrowed but live.** The bot message half is shipped (`0a90650`). What remains:
`submit_ad` still returns `tuple[bool, list[str]]`; `process_preview` still `state.clear()`s on
the expired path; the bot still probes the database to discover the outcome.

**Corrections absorbed** (§1): **the expired string and its `ru`/`bs` translations already
exist** — `process_preview` already renders the dedicated translated expired string —
**reuse, never author**. **`apps/ads/services/` has no `__init__.py`**, so the source plan's
*"re-export through `__init__.py` and `__all__`"* is **unexecutable** (correction 11).
**`PHOTO_UNAVAILABLE` already exists** as the **third** `False` return (correction 4). **R-5 /
R-14** — `03-DB-004`'s `OperationalError` handling lives in the **handler**, and the enum must
**not** absorb it.

**Agent roster.**
- **Implementor — yes.**
- **Auditor — yes.** Must re-derive every `submit_ad` call site (3 production + 11 test) and
  classify each against the five outcomes; the plan's churn estimate depends on the real count.
- **Researcher — no.** Q12 is **closed**.
- **Planner — no.** The result shape is decided and mirrors an existing in-repo idiom.
- **Validator — yes.** The change rewrites a service's **public return contract** and every
  caller. An independent review must confirm no caller was missed and that no outcome was
  collapsed back into a boolean.

**Decision gate — Q7. OPEN, routed to the coordinator, non-blocking.** Q7 decides the **size** of
this block: fold the `_pass_moderation` branch in, file it as a new finding owned by phase 03, or
defer it. **BLOCK 12 ships either way**, and the disposition is recorded in the commit message
even if the answer is "deferred". See §2 Q7.

**Decision gate — Q12. CLOSED by the source plan §0.6.1. Recorded, not re-opened.**

> **Closed decision.** `SubmitAdOutcome(StrEnum)` + `SubmitAdResult(NamedTuple)`, **both in
> `apps/ads/services/submission.py`**, mirroring the existing `ConsumeOutcome` / `ConsumeResult`.
> Five members: `PUBLISHED`, `MODERATION_FAILED`, `PHOTO_UNAVAILABLE`, `DRAFT_GONE`,
> `INVALID_TRANSITION`. **The lock timeout stays an exception** — the enum houses business
> outcomes only.
>
> **Rationale.** The plan's *"NamedTuple is near-zero churn"* is **wrong**, and its *"Option C has
> the largest churn"* is only true for a dataclass: a 3-field result **cannot** be 2-tuple-
> unpacked, so 3 production + 11 test sites change mechanically. It is still the best option.
> Rejected: a sentinel string (crosses a translation boundary, rule 10); a 2-field legacy shim
> beside a 3-field variant (two public contracts for one service); a dataclass (a second result
> idiom in a repo with two `NamedTuple` results); Pydantic (rule 11 — a result is not a boundary
> input).

**File surface (semantic units).**
- `src/backend/apps/ads/services/submission.py` → the module-level `SubmitAdOutcome` (new),
  `SubmitAdResult` (new), and `submit_ad`'s return statements. **No `__init__.py` is created;
  `services/` is an implicit namespace package and no `__all__` is added.**
- `src/backend/apps/ads/views/edit.py` → `ad_edit`'s use of `submit_ad`'s result (**read the
  call site; it renders `errors[0]`**).
- `src/telegram_bot/handlers/ad_create/submit.py` → `process_preview` (the `state.clear()` on
  the expired path; the `errors` it currently discards).
- `src/telegram_bot/handlers/ad_edit/confirm.py` → its `SubmitAdInput` construction site.
- `src/backend/apps/ads/tests/test_submission.py`; `src/telegram_bot/tests/`'s ad-create and
  ad-edit tests (the 11 mechanical call-site changes).
- Locale: `ru`, `bs`, `en` `.po` — **append only**; reuse the two existing strings.

**Constraints.**
1. **`OperationalError` must NOT become an outcome member (R-5, R-14).** `03-DB-004` landed the
   handler-layer catch in `ad_edit` and `process_preview`. `submit_ad` may raise it; the **handler
   owns it**. If this block wraps `submit_ad` in a blanket handler, it **double-handles** a
   condition the handler layer already owns. **The documented boundary between business outcomes
   and exceptions is part of the deliverable.**
2. **The `else` branch is reached for photo-unavailable too, not only for an expired draft.**
   That is the third `False` return and it is `PHOTO_UNAVAILABLE`'s home.
3. **The asymmetric blast radius is confirmed:** `ad_edit` renders `errors[0]`, while the bot
   **discards** `errors` and probes the database to discover the outcome. BLOCK 12 removes the
   probe.
4. **Reuse, never re-author.** Two strings exist and must be reused: `"Your draft expired and was
   deleted. Please start again with /post."` and — only if BLOCK 11 proceeds, which it does not —
   `"Failed to copy ad."`.
5. **`.po` files are append-only.** Never run a wholesale `makemessages` — it would discard a
   concurrent phase's additions. `ru` **and** `bs` `msgstr` must be non-empty; `en` may be empty.
6. **`state.clear()` on the expired path** is the FSM defect: the bot forgets the conversation and
   the seller cannot retry. Fixing the *reason* the code takes that branch is what BLOCK 12 does;
   clearing the state unconditionally is not.

**Tests required.**
- *Must be **rewritten* (mechanical, project rule 2 where the boolean unpack breaks):** the
  3 production and 11 test `submit_ad` call sites that unpack `tuple[bool, list[str]]`.
- *Must be added:* each of the five outcomes asserted through `submit_ad`, with the outcome
  **and** the carried data — not merely that a boolean came back.
- *Must be added:* `process_preview` does **not** `state.clear()` on the expired path — the
  seller can retry.
- *Must be added:* the bot no longer probes the database to discover the outcome (it acts on the
  returned outcome directly).
- *Must be added:* `PHOTO_UNAVAILABLE` is reachable and distinct from `MODERATION_FAILED` and
  `DRAFT_GONE`.
- *Must be added:* an `OperationalError` raised inside `submit_ad` **propagates** — it is not
  converted into an outcome. This is the direct guard for constraint 1.
- *Must keep passing unchanged:* `test_i18n_completeness.py`, `test_i18n_pipeline.py`,
  `test_bot_no_hardcoded_messages` (the AST scan over every `.py` under
  `telegram_bot/handlers/`).

**Docker gate command.**
```
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/ src/telegram_bot/tests/" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```

**Risk / rollback.** A caller is missed and unpacks three fields as two — the migration count is
the risk (mitigation: the Auditor's full call-site inventory, and the full fast suite). The
lock-timeout boundary is blurred (mitigation: the propagation test). **Rollback:** the result
shape change and all its call sites revert **together** — reverting one leaves a red tree.

---

### BLOCK 13 — Seller-scoped photo dedup returns another ad's row

| | |
|---|---|
| **Findings owned** | `AD-006` |
| **`depends_on`** | — (owner-gated on Q6) |
| **Priority** | was P2; **live but not pre-empted** |
| **Readiness** | **OWNER-GATED (Q6) — LIVE: `MEDIA-002` has NOT been executed** |

**The gate is genuinely open and genuinely live.** `MEDIA-002` has **not** been executed:
`AdImageService.create_or_skip` still filters
`AdImage.objects.filter(sha256=digest, ad__user_id=ad.user_id)` with a *"Deduplication is scoped
per seller"* docstring, and `submit_ad` still discards the return value. Phase 07's **BLOCK 2**
(`MEDIA-001`) is retired by `64a9de6`, but its **BLOCK 1** is untouched. Options restated at
§2 Q6.

**Facts the owner needs for the tie-breaker (all verified at the anchor).**
- A duplicate is detected **after** `move_staging_to_permanent` has already moved the file, and
  `submit_ad` discards the returned row — so the promoted file is on disk with **no** `AdImage`
  row pointing at it, reclaimed later by `sweep_orphaned_media`. **Re-scoping the lookup alone
  does not fix that**; it makes it the *normal* case, because a seller posting the same photo to
  two ads is no longer unusual. Whichever record wins **must state whether it addresses the
  orphan**.
- The ≥1-photo gate **does** exist — `auto_moderation.py::_validate_image_count` against
  `ModerationCriteria.min_images` (default 1). So a **full** dedup hit lands the ad in
  `ON_MODERATION_FAILED`; **the real symptom is a *partial* hit publishing the ad with fewer
  photos than uploaded** — not caught by `min_images`.
- The "broken image" symptom was **refuted** by phase 07: `ad_list.html`, `detail.html` and
  `dashboard.html` all guard with `{% if ad.images… %}`; `admin/moderation/review.html` renders
  `{% trans "No photos" %}`.
- `test_ad_image_service.py` has an `isolated_media_root` fixture — the cheap regression harness.
- **R-15:** `03-DB-005` **has** landed (`35441e0`) with the shape `plan_staging_promotion` (pure,
  key-rewriting before the transaction) + `promote_media_files` in `transaction.on_commit`. The
  source plan does not state which option it recorded. **The Implementor must re-read phase-03
  BLOCK 8's recorded option before designing the reclaim.** Phase 07 already decided the shape:
  prune `permanent_keys` **in place**; `on_commit` reclaim **against `STAGING_PREFIX + key`**,
  because `delete_photo(permanent_key)` is a **silent no-op**.

**Ships regardless of Q6: nothing production-side.** The recorded tie-breaker and the recorded
gate are themselves the deliverable. Under the `MEDIA-002` answer the block becomes a
cross-reference plus a check that phase 07's fix covers the ads-side call site.

**Agent roster** (applies only once Q6 opens in favour of `AD-006`).
- **Implementor — yes**, only then.
- **Auditor — yes** — confirm the reclaim design against phase-03 BLOCK 8's recorded option.
- **Researcher — yes** — the dedup/reclaim interaction is a genuine two-shape question with
  different orphan behaviour.
- **Planner — yes** — the reclaim touches the FS-after-commit rule (code context §6.5).
- **Validator — yes** — it changes what gets deleted from storage.

**Constraints.** TX-then-FS: filesystem side effects happen **only** after commit, via
`transaction.on_commit()`. Never `unlink`/`move` inside `transaction.atomic()`. The
`except Exception` inside any cleanup carries `# noqa: BLE001 — never let FS failure break the
cascade` and `logger.exception` (matching `apps/media/signals.py`).

**Tests required (only under the `AD-006` answer).**
- *Must be added:* the **cross-ad, same-seller** case — two ads of one seller sharing a `sha256`
  — which is the coverage phase 07 refuted as existing.
- *Must be added:* the **orphan reclaim** — a promoted file with no row is reclaimed, and the
  reclaim targets `STAGING_PREFIX + key`.
- *Must keep passing unchanged:* `test_ad_image_service.py::TestAdImageServiceCreateOrSkip::test_returns_existing_duplicate_same_user`
  — it uses the **same ad twice** and stays green under a re-scope (correction 6, confirmed).

**Docker gate command** (only if the block proceeds):
```
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/ src/backend/apps/core/tests/" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```

**Risk / rollback.** Shipping the minimal `AD-006` fix **alongside** `MEDIA-002` produces two
patches for one predicate — the exact `VAL-004` hazard. **This is the block's principal risk, and
it is why the gate must be answered before any code.** **Rollback:** filesystem effects are
post-commit, so a revert leaves promoted-but-unreferenced files, which `sweep_orphaned_media`
reclaims.

---

### BLOCK 14 — Records

| | |
|---|---|
| **Findings owned** | records: `AD-003` (retired), `AD-004`/`AD-005`/`AD-007`/`AD-012`/`AD-015`, `VAL-001` boundary, `VAL-004` (moot), `VAL-005`/`VAL-006` answers |
| **`depends_on`** | BLOCK 7 (soft — the `VAL-005` answer depends on Q4; `db-retention.md` is shared) |
| **Priority** | P1 — documentation-only |
| **Readiness** | **READY-WITH-CORRECTIONS — RECORD-ONLY (no production code)** |

**Agent roster.**
- **Implementor — yes** — documentation is still written by someone. Exactly one at a time.
- **Auditor — no.** There is nothing to re-derive: every record below is a **measured** fact with
  a named commit.
- **Researcher — no.**
- **Planner — no.** No design is open here; the records state measured facts and owner answers.
- **Validator — yes** — a record that contradicts a shipped doc is the whole risk class of this
  block (R-9, R-21), and only an independent reader catches it.

**Files edited by this block (documentation only).**

| File | What changes | Why |
|---|---|---|
| `docs/02-database/db-retention.md` | *"Proper refcounting (`AD-003`) is still open"* → reconciled with the `AD-003` retirement; **and** the duplicated `deleted_at` / `deleted_at is older than 120 days` fragment repaired | **R-9** — the shipped doc contradicts the retirement record; the fragment is a live one-line defect |
| `docs/02-database/db-schema.md` | Record that the bare `AD-005` at its `archived_at` comment is a **fourth `VAL-001` instance outside BLOCK 1's surface**, and that the repository-wide legacy-citation sweep is **not** phase 05's | **R-7 / C-6** — recording the boundary prevents a future implementer "fixing" it without authority |
| The phase-05 findings record | `AD-003` **RETIRED**, evidenced by `64a9de6`, mechanism = **existence check at delete time, not a stored refcount** (C-4); `AD-005` **already fixed** by `664b572`; `AD-007` **moot** by `2697796`; `AD-012` **already fixed (both halves)** by `ba1b059`; `AD-015`'s `UserAdmin` half **already fixed** by `a19a0ee`, behaviour half OPEN and unowned (R-21); `VAL-004` **moot — resolved and shipped** by `64a9de6`; the two record-only candidates from §1 | §1, R-9, R-21, and the phase 05 report's disposition tally |
| The `VAL-005` / `VAL-006` answers | Record the owner answers when they arrive, or **record them as "open — deferred"** with the consequence | A gate never closes silently (§2) |
| `technical-specification.md` attribution | Re-word: *"reserved to phase 06; `PII-113` **not yet landed**"* | **C-24** — the constraint binds; the attribution is unevidenced |

**Constraints.**
1. **Never infer a cycle number.** Prefer the descriptive form over a guessed attribution. The two
   new candidates from §1 get **no** cycle number.
2. **This block edits documentation only.** No production code, no migration, no test.
3. **`technical-specification.md` must not be edited** — only the *attribution* is corrected in a
   phase-05 artefact.
4. **`db-retention.md` is shared with BLOCK 7** (§5). BLOCK 14's edit is the `AD-003` sentence and
   the duplicated fragment; BLOCK 7's edits are the retention table row, the sweep table row and
   the index entry. **BLOCK 14 lands first**; BLOCK 7 re-reads before it starts.
5. **`AD-015`'s behaviour defect stays OPEN and unowned** — phase 06 `PII-104` + `VAL-003` and
   phase 15 `AUTHZ-005`. Phase 05 must **not** implement it: it would require
   `ListingsQuery.build_queryset` to gain an `ads_auto_publish` term, which is phase 15's surface.
6. **Re-derive the disposition tally from §0.1 of this document**, never from the source plan's
   §0.4/§8.1 counts (C-1).

**Tests required.** None of its own. `test_i18n_completeness.py` must still pass if any English
string was added to a scanned surface — **documentation files are not scanned**, but confirm.

**Docker gate command:**
```
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```

**Risk / rollback.** A record contradicts a shipped doc (mitigation: the Validator; R-9 and R-21
are the two known instances). An owner gate is recorded as closed when it is not (mitigation: the
"open — deferred" wording is mandatory). **Rollback:** documentation-only; revert the commit.

---

## §4. Dependency graph

### §4.1 Serial order

**One Implementor at a time** (`.kilo/rules/commands.md`). The order below is the execution
order; §4.2 names every hard edge.

| # | Block | Findings | Hard edges in | Gate |
|---|---|---|---|---|
| 1 | **BLOCK 1** — hoist matrix, uniform `archived_at` clearing, disambiguate 2 IDs | `AD-013`, `AD-011`, `VAL-001` (part) | — | — |
| 2 | **BLOCK 2** — price/photo edit restarts the publish clock | `AD-009` | `1 → 2` | Q3 **closed** |
| 3 | **BLOCK 3** — restore the human approval path | `VAL-003` | — | — |
| 4 | **BLOCK 4** — suite reaches `ON_MODERATION` honestly | `VAL-002` | `3 ⇢ 4` (soft) | Q10 value (block-internal) |
| 5 | **BLOCK 9** — bulk moderation: tx, lock, honest errors | `AD-010` | — | Q11 **closed** |
| 6 | **BLOCK 10** — `AdImage.position` uniqueness | `AD-014` | **`7 → 10`** | Q9-sizing **closed** |
| 7 | **BLOCK 12** — expired draft is not a moderation failure | `AD-016` | — | Q12 **closed**; Q7 open (non-blocking) |
| 8 | **BLOCK 14** — records | records | `14 ⇢ 7` (soft, `db-retention.md`) | — |
| 9 | **BLOCK 7** — retention anchor, predicate, index | `AD-004`, `VAL-005` | **`4 → 7`** (C-15); `7 → 10` | **Q4** |
| 10 | **BLOCK 6** — one sanctioned admin write path | `AD-001` | **`1 → 6`**, **`3 → 6`** | **Q1** |
| 11 | **BLOCK 5** — make `ON_MODERATION` durable | `AD-008` | **`3 → 5`**, **`4 → 5`** | **Q2** |
| 12 | **BLOCK 8** — editing a failed ad | `AD-002` | **`1 → 8`** | **Q5** (8A ships regardless) |
| 13 | **BLOCK 13** — seller-scoped dedup | `AD-006` | — | **Q6** |
| — | **BLOCK 11** — `ad_copy` | `AD-012` | — | **MOOT-SUPERSEDED** — record only, no position |

**Why this order is not the source plan's.** The source plan orders BLOCK 5, 6, 7, 8 and 13 in
their numeric slots; they are **owner-gated**, so they cannot hold the queue. They are placed at
the **tail** so the ungated work drains first. The ungated sub-graph — 1 → 2 → 3 → 4 — is exactly
the source plan's prefix and is unchanged.

### §4.2 Every hard edge, and why it exists

| Edge | Kind | Why |
|---|---|---|
| **`1 → 2`** | HARD (technical) | BLOCK 2 must add a transition edge and must not introduce a third divergent timestamp-clearing idiom. Both are impossible while the matrix is a function-local literal |
| **`1 → 6`** | HARD (technical) | BLOCK 6's sanctioned write path routes through `Ad.transition_to`; the closed Q8 decision changes its return type. The matrix must be a named value first |
| **`1 → 8`** | HARD (technical) | BLOCK 8B adds `ON_MODERATION_FAILED → ON_MODERATION` to `ALLOWED_TRANSITIONS`. A module-local literal cannot be extended from another module |
| **`3 → 6`** | HARD (safety — the catastrophic one) | If `AdAdmin.status` goes read-only while `bulk_approve` / the approve view are dead, **moderators lose the ability to publish entirely**. Two independent guards: the edge, and BLOCK 6's internal ordering (read-only lands **last**) |
| **`3 → 5`** | HARD (semantic) | `AD-008` makes `ON_MODERATION` real. If the approval path is still dead when it does, the state becomes observable and unusable. "The approval path must exist for the state to be worth having" |
| **`3 ⇢ 4`** | SOFT | They share test files — BLOCK 3 retargets `TestApproveAdView` and `TestBulkOperations`, which are also in the census. **Soft, not hard:** BLOCK 4's own hard edge is forward, to BLOCK 5 |
| **`4 → 5`** | HARD (rollout safety) | `VAL-002` is a defect in the **oracle**. If BLOCK 5 lands first, roughly half the fabricated tests stay green — passing against a state that has just become real — and the suite would report success while validating **nothing** about durability. BLOCK 4's green state must be established **after a recorded red baseline** |
| **`4 → 7` — NEW (C-15)** | HARD (resource contention) | Under Q4 options (i)/(ii) the whole of `test_sweep_delete.py` goes red, and the fix is **`src/backend/conftest.py::_set_status_timestamp`** — BLOCK 4's reserved file. `_set_status_timestamp` stamps **`archived_at` only** for `ARCHIVED`; the file's cases create `ARCHIVED` rows with `published_at IS NULL`, which fails `published_at__lt=cutoff`. **Two blocks now claim the most contended file in the repository** |
| **`7 → 10`** | HARD (resource contention) | Both blocks create an **`apps/ads`** migration. BLOCK 7 takes the next free number (`0009_*` at the anchor); BLOCK 10 must take what is free **after** it. **Two migrations with the same number in one app is a hard failure, not a merge conflict** |
| **`14 ⇢ 7`** | SOFT (file sharing) | Both edit `docs/02-database/db-retention.md` — BLOCK 14 the `AD-003` sentence and the duplicated fragment; BLOCK 7 the retention table row, the sweep table row and the index entry. BLOCK 14 lands first; BLOCK 7 re-reads |
| **`5 ⇢ 12` via Q7** | HARD (consequence) | Q7 must be **answered before BLOCK 5 option (i) ships**. Under (i), `_pass_moderation`'s bare handler would mark an ad failed for a **system** error in a **second** transaction with **no** compensation. This is the one place BLOCK 5 and BLOCK 12 genuinely interact — and it is why BLOCK 12's Q7 is not a free choice |

### §4.3 No edge exists for these, and why

| No edge | Reason |
|---|---|
| **BLOCK 5 ⇢ BLOCK 6** | BLOCK 6's *unconditional* half does not touch the state machine, and its gated half is decided by **Q1**, not by BLOCK 5's landing. BLOCK 8B has the same relationship — if BLOCK 6 lands first, the fix has **one** place to live; if not, BLOCK 6 must adopt it. **Record which, in the commit message** |
| **BLOCK 13 ⇢ phase 07** | The ordering is the **Q6 gate**, not an edge. Under the `MEDIA-002` answer, BLOCK 13 ships no code at all and becomes a cross-reference |
| **BLOCK 2 ⇢ BLOCK 7** | Resetting the clock is correct under **every** candidate anchor, so BLOCK 2 is not blocked on Q4. Changing the *window* is BLOCK 7's job |
| **BLOCK 9 ⇢ BLOCK 3** | Different surfaces, different services, different test classes. BLOCK 9 touches the JSON endpoint; BLOCK 3 touches `bulk_approve` and the review views |
| **BLOCK 12 ⇢ BLOCK 2** | Different services and different outcomes. The only interaction is the shared call-site inventory in `submission.py` |
| **Anything ⇢ BLOCK 11** | It is moot. It has no dependents and no code |

---

## §5. Shared artefacts and contended files

Every file more than one block — or another phase — claims. **One Implementor at a time** makes
serial execution the primary control; the rules below are the secondary control.

| Artefact | Claimed by | Rule |
|---|---|---|
| **`src/backend/conftest.py`** | **BLOCK 4** (`create_test_ad`, `create_test_ads_bulk`); **BLOCK 7** (`_set_status_timestamp`, under Q4 (i)/(ii) — **new**, C-15); **phase 03** (must not edit at all); phase 04 (has shipped edits) | **The most contended file in the repository.** BLOCK 4 changes **only** the `status` default and nothing else. BLOCK 7 changes **only** `_set_status_timestamp` and **only** if Q4 lands on (i)/(ii). The two are **serialised by the `4 → 7` edge**. Every edit: re-read immediately before, change only the named symbols, stage by explicit path. If either block finds an unexplained change, **stop and report to the coordinator** |
| **`src/backend/apps/ads/models.py`** | **BLOCK 1** (`ALLOWED_TRANSITIONS`, `transition_to`), **BLOCK 2** (`reset_publish_clock`, the matrix), **BLOCK 6** (`transition_to` return type), **BLOCK 7** (`Ad.Meta.indexes`), **BLOCK 8** (the `ON_MODERATION_FAILED` matrix entry) | **Serialised** by `1 → 2`, `1 → 6`, `1 → 8`. BLOCK 1 goes **first** and owns the extraction; every later block adds to an already-hoisted value. **BLOCK 7's `Ad.Meta.indexes` change is on `Ad`, not `AdImage`** — it must not disturb BLOCK 10's `AdImage.Meta.constraints` |
| **`src/backend/apps/ads/services/submission.py`** | **BLOCK 5** (`submit_ad` transaction), **BLOCK 12** (`SubmitAdOutcome` / `SubmitAdResult` / `submit_ad` returns), **BLOCK 13** (`create_or_skip` call site), BLOCK 8 (read, unless retry bounding lands there) | **BLOCK 12 first** (the return-contract change), then BLOCK 5 (the transaction), then BLOCK 13. **Each must re-read `submit_ad` after the previous block lands** — its shape changes twice |
| **`src/backend/apps/ads/views/edit.py`** | **BLOCK 2** (`ad_edit`), **BLOCK 5** (`ad_reactivate`), **BLOCK 8** (`ad_edit` catch-all), BLOCK 12 (the `submit_ad` call site) | Serialised by the block order. **BLOCK 8 must not touch the reactivation or text branches** |
| **`src/backend/apps/ads/tests/test_edit.py`** | **BLOCK 2** (`TestPublishedTextEdit`), **BLOCK 8** (`TestEditOtherStatusDirectSave`) | **Two different classes.** BLOCK 8 must not touch `TestPublishedTextEdit` |
| **`src/backend/apps/moderation/admin_actions.py`** | **BLOCK 3** (`bulk_approve`, `approve_ad` filters), **BLOCK 9** (read — the endpoint delegates), BLOCK 6 (read, unless Q8 forces a new writer) | BLOCK 3 owns the filter changes; BLOCK 9 and BLOCK 6 **read only**. `bulk_reject`, `bulk_ban_users`, `bulk_delete`, `soft_delete_ad` are **read only** for BLOCK 3 |
| **`src/backend/apps/moderation/tests/test_moderation_views.py`** | **BLOCK 3** (`TestApproveAdView`, `TestModerationReviewLocking`), **BLOCK 4** (census — 1 omission, 16 explicit `ON_MODERATION` sites) | **The only file in both channels.** BLOCK 3 first, then BLOCK 4's census. `TestModerationReviewLocking` is **keep-green in both** |
| **`src/backend/apps/moderation/tests/test_admin_actions.py`** | **BLOCK 3** (`TestBulkOperations`), **BLOCK 9** (read — the tripwire), BLOCK 4 (census) | `TestBulkLockingStructure` is **keep-green throughout**; its `test_bulk_ban_users_not_locked` is **phase 03's** tripwire (C-16) |
| **`src/backend/apps/core/management/commands/delete_sweep.py`** | **BLOCK 7** only | Phase 03's `03-DB-008` never touched it (C-17) and `03-DB-011` already removed its `storage_keys` pre-collection (C-18). **Single-owner.** BLOCK 7 must not add per-batch commits (C-19) |
| **`src/backend/apps/core/tests/test_sweep_delete.py`** | **BLOCK 7**, **phase 03** (an owner) | **Whole-file blast radius** under Q4 (i)/(ii). Re-read before editing |
| **`src/backend/apps/core/tests/test_sweep_lock_structure.py`** | **BLOCK 7** (must stay green), phase 03 (`e61555f`) | **Nobody edits it.** It pins `_SESSION_SCOPED_BATCHERS = {"archive_sweep", "recompute_normalized_prices"}`, asserts `delete_sweep` is `in_atomic is True, session is False`, and pins `EXPECTED_SWEEP_COMMANDS` by **name-set equality** |
| **`docs/02-database/db-retention.md`** | **BLOCK 7** (table rows), **BLOCK 14** (the `AD-003` sentence, the duplicated fragment), phase 03 (`815a670`, `7763625`) | **BLOCK 14 first**, then BLOCK 7 re-reads. Separate symbol-level edits |
| **`docs/02-database/db-schema.md`** | **BLOCK 1** (the `VAL-001` boundary record), **BLOCK 2** (**verification only** — C-14), phase 03 | **Must never be corrected backwards** (C-14). BLOCK 2 verifies; BLOCK 1 records |
| **`docs/01-spec/technical-specification.md`** | **Phase 06 only** | **Binding prohibition** on every phase-05 block. The *attribution* to `PII-113` is unevidenced (C-24) — re-word the attribution, do not edit the file |
| **`src/backend/apps/users/admin.py`** | **Phase 04 only** | **Binding prohibition.** `a19a0ee` landed the `UserAdmin` fix and deliberately left the `has_*_permission` bodies byte-identical. Phase 05 ships **nothing** here (R-20, R-21) |
| **`src/backend/apps/media/**`** | **Phase 07 only** | **Binding prohibition.** `64a9de6` is phase 07's `MEDIA-001` |
| **`src/backend/apps/core/enums.py`** → `AdvisoryLockId` | **Phase 05 allocates none** | If one is ever forced: `enums.py`, the allocation table in `apps/core/utils/advisory_lock.py`'s docstring and `apps/core/tests/test_advisory_lock_ids.py` change in **one** commit, and the coordinator is told **first**. **19** members today; **ID 10 is unallocated** (R-10) |
| **`src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po`** | **BLOCK 8** (link gating), **BLOCK 12** (outcome strings), phase 06 | **Append only.** Never a wholesale `makemessages`. `ru` **and** `bs` `msgstr` non-empty; `en` may be empty |
| **`.ai/audit/**`** | **Nobody** | Unmodifiable by mandate |
| **`.ai/plans/01–16`** | **Their own Planners** | This plan edits only `.ai/plans/17-ad-lifecycle-execution.md` |

---

## §6. DoD for the whole execution

### §6.1 Scope

1. Every in-scope finding is dispositioned exactly once in §0.1, with a HEAD status traceable to
   the code context §2 and a commit cited where one exists.
2. **No finding is re-shipped.** `AD-005`, `AD-007`, `AD-012` (both halves) and `AD-003` ship
   **nothing**. BLOCK 11 records, it does not patch.
3. **No speculative redesign.** The only scope added beyond the source plan is BLOCK 14's
   `db-retention.md` reconciliation (R-9) and BLOCK 8A's allow-list conversion (the source plan's
   §4.4 explicitly left this split to the Planner). Everything else is the source plan's scope,
   corrected.
4. **Every target is a semantic symbol** — no task, commit, or record names a line number as a
   target.

### §6.2 Gates

5. **Q1, Q2, Q4, Q5, Q6 are not decided by any agent in this execution.** If unanswered, each is
   recorded as **"open — deferred"** with its §2 consequence. **A gate never closes silently.**
6. **Q3, Q8-mechanism, Q9-sizing, Q11, Q12** are recorded as closed, with the source plan §0.6.1
   rationale carried verbatim, and are **not re-opened by an Implementor**.
7. **Q7, Q8-value and Q10-value** are recorded as open with their options and their resolution
   owner.

### §6.3 Per-finding behavioural confirmation

Each of these must be demonstrated **red before the fix and green after**, by a test that asserts
**logic and component interaction** — never the absence of a variable, a log string, or a line
count:

| Finding | The behavioural assertion that closes it |
|---|---|
| `AD-001` | Violation 4: a POST selecting `REJECTED` / `ON_MODERATION_FAILED` returns a **validation error, not an HTTP 500**. Violations 1–3: the audit row exists, `original_published_at` is immutable, `user` is not reassignable |
| `AD-002` | The five-status enumeration test, **plus** (under Q5 (b)) that `moderation_failed_at` is reset and `purge_failed_ads` does not reclaim the rewritten content — the only assertion that proves the finding is **fixed**, not hidden |
| `AD-004` | A manual archive back-dated 61 days is selected/not-selected **per the chosen anchor**, **and** the auto path still fires at `published_at + 120 d` |
| `AD-006` | The **cross-ad, same-seller** case, **plus** the orphan reclaim — only under the `AD-006` answer to Q6 |
| `AD-008` | A durably `ON_MODERATION` ad observed from a **separate connection**, **and** a crash leaves it recoverable. **Without both, option (i) is not shippable** |
| `AD-009` | A price-only edit moves `published_at` **strictly forward** on a **reloaded** instance |
| `AD-010` | Each of the six failure classes through the endpoint, with `completed` counting only what succeeded |
| `AD-011` | `ARCHIVED → PUBLISHED` leaves `archived_at is None` **in the database**, on a reloaded instance, and the DB rejects a stale `archived_at` |
| `AD-013` | The matrix-identity test — seven source keys and their target sets match the shipped matrix |
| `AD-014` | The database **rejects** two `AdImage` rows on the same `(ad, position)` |
| `AD-015` | Behaviour half remains OPEN and unowned; **no phase-05 test** |
| `AD-016` | Each of the five outcomes with its carried data; `process_preview` does **not** `state.clear()`; and an `OperationalError` **propagates** rather than becoming an outcome |
| `VAL-001` | The two bare IDs in `transition_to` are namespaced; the `db-schema.md` instance is **recorded, not fixed** |
| `VAL-002` | The regression guard that no test fabricates `ON_MODERATION` through the fixture without an explicit `status=`, **red against the pre-fix conftests** |
| `VAL-003` | `bulk_approve` returns a **non-zero** count on a genuinely-approvable ad with the audit row and `published_at` written; the approve view returns **2xx**; a status outside the pair is refused with a message |
| `VAL-005` | The owner answer recorded, and the **fifth** conflict (§6.6) recorded alongside it |
| `VAL-006` | The owner answer recorded; the write-path ownership statement recorded |
| `AD-003`, `AD-005`, `AD-007`, `AD-012`, `VAL-004` | **Already shipped** — the evidence commit is recorded and the shipped tests keep green. No new test |

### §6.4 Cross-phase integrity

9. **Nothing from `apps/users/admin.py`, `apps/media/**`, or
   `docs/01-spec/technical-specification.md` is edited.**
10. **No `is_ads_visible` term and no `ads_auto_publish` term** is added to
    `ListingsQuery.build_queryset`.
11. **No `AdvisoryLockId` member is allocated.**
12. **No `ModeratorActionLog` migration** in this phase — the model has **no moderator column**
    (correction 8); it is filed separately.
13. **No per-batch restructure in `delete_sweep`** (C-19), and no `03-DB-008` re-do.
14. **`src/telegram_bot/tests/conftest.py` is not edited** (C-22) — it does not define the
    fixtures.
15. **The 63-site census, the 40-occurrence grep, the 9 matrix-valid fabricators and the "2
    production + 1 cleanup" split are recorded verbatim** wherever BLOCK 4 writes them down.

### §6.5 Project conventions

16. **English only** (rule 1). **No `print()`** — `logger = logging.getLogger(__name__)` (rule 12).
17. **`StrEnum` for all constants** (rule 10): `AdvisoryLockId`, `AdStatus`,
    `ModeratorActionType`, `SubmitAdOutcome`, `BulkModerationAction` are enums; `SEEDABLE_AD_STATUSES`
    is a `frozenset`. **No bare strings, no dict-of-strings.** New migrations and choices are
    declared in `apps/core/enums.py` or `apps/ads/models.py`.
18. **Pydantic v2 only at boundaries** (rule 11): `SubmitAdInput`, `AdEditInput`,
    `SubmittedPhoto`, settings schemas. **Never inside a service body.** `SubmitAdResult` is a
    `NamedTuple`, **not** Pydantic — a result is not a boundary input.
19. **Composition over inheritance** (rule 6); **follow existing patterns** (rule 7); **no new
    `__init__.py`** in `apps/ads/services/` (it is an implicit namespace package) and **no
    `__all__`**.
20. **TX-then-FS** (code context §6.5): filesystem side effects only via `transaction.on_commit()`,
    never inside `transaction.atomic()`. Never `unlink`/`move` in a transaction.
21. **`@sync_to_async`** at default `thread_sensitive=True` for every bot DB call. **Do not "fix"
    a lock wait by raising the worker count.**
22. **Service-boundary rule** (rule 3): new business logic goes in a `services/` module, never in a
    view, handler or `ModelAdmin` method body. **`apps.*` must never import `telegram_bot.*`.**
23. **The `atomic()` pyright-suppression convention:** match the **file's** existing wording —
    three variants exist (canonical; canonical + appended rationale in `admin_actions.py`; the
    short variant in `edit.py`). **Never write a bare suppression.**
24. **i18n is part of DoD** (rule 16): `ru` **and** `bs` `msgstr` non-empty for every new
    user-visible string; `en` may be empty. **Append only.**

### §6.6 Corrections to the stale figures — the authoritative numbers

Any report, commit, or task YAML that carries the source plan's figure is **wrong**. The
authoritative values:

| Quantity | Source plan says | **Authoritative** |
|---|---|---|
| `basedpyright src/` | 12 errors in 2 files | **0 errors, 0 warnings, 0 notes** (scope fix `8bf0517` adds `telegram_bot`) |
| `_QUERY_BOUND` in `test_ad_detail_queries.py` | 16 (two locations) | **19**, with an explicit *"Do NOT re-tighten this to 16"* comment |
| `VAL-002` census | "34" / "~62" / "~62/93" | **63 omission sites in 7 files** (62 backend + 1 bot); explicit grep **40** (2 production + 1 cleanup + **37** test); Channel C **12** (2 production + **9** test + 1 near-miss) |
| Backend call sites passing `status=` | not stated | **560 of 622** (81.0 %) |
| Finding tally | 14 live, "1+4+8+3" | 14 fully open at the report's anchor, **11 live `AD-*` at HEAD** — re-derive from §0.1 |
| `create_test_ad` definition sites | 2 ("both conftests") | **1** — `src/backend/conftest.py` only |
| `AdvisoryLockId` members | 18 | **19** (ID 10 unallocated; `TEST_SCHEMA_SETUP = 111` is new) |
| `ModeratorActionType` members | 4 | **5** (`REJECT`, `BAN_ACCOUNT`, `SOFT_DELETE`, `CRITERIA_CHANGE`, `OTHER`) |
| `TestPublishedTextEdit` methods | not stated | **6** |
| `ALLOWED_TRANSITIONS` source keys | 7 | **7** ✓ (re-confirmed at the anchor) |
| `VAL-001` bare IDs in `transition_to` | 3 | **2** (`DB-003` rewritten by `fd8c423`) + **1** recorded outside the file surface |
| Next `apps/ads` migration | `0008_*` | **`0009_*`** — and **`__pycache__` is not the authority** (R-19) |
| `test_bulk_ban_users_not_locked` location | `apps/users/tests/` (phase 04) | **`apps/moderation/tests/test_admin_actions.py`** — **phase 03's** (`DB-003`) |
| BLOCK 2's "photo-only edit" test | required | **unimplementable** — no `request.FILES` exists in any `.py`; filed as a record-only candidate |
| `technical-specification.md` attribution | phase 06 `PII-113` | **reserved to phase 06; `PII-113` not yet landed** |

### §6.7 Deliverables

25. This file is the **single status surface**; §7 is the block status log.
26. Each block's task YAML is shaped by `.ai/tasks/templates/task_template.yaml` and carries
    `source_reference: .ai\plans\17-ad-lifecycle-execution.md` and
    `source_section: "BLOCK N — <title>"`.
27. Every commit message states: which findings it closes, which **shipped-green test it rewrote
    and why** (project rule 2), which owner gate it is **not** deciding, and any cross-phase
    boundary it honoured.
28. The phase report re-derives its disposition tally from **§0.1 of this file**, never from the
    source plan's counts.
29. **All gates are reported by name and state.** An open gate is a deliverable, not an omission.

---

## §7. Block status log

**Initially empty. The Tech Lead fills this in as blocks land.** One row per block; a block is
only marked complete when its **whole** Docker gate command has passed and its §6 DoD items are
met. A block that ends mid-sequence is **never** marked complete.

| Block | Readiness | Status | Commit | Notes |
|---|---|---|---|---|
| 1 | READY-WITH-CORRECTIONS | not started | — | |
| 2 | READY-WITH-CORRECTIONS | not started | — | Q3 closed as B′; photo-only test filed record-only |
| 3 | READY | not started | — | `TestModerationReviewLocking` added to keep-green (C-21) |
| 4 | READY-WITH-CORRECTIONS | not started | — | Census: 63 sites / 7 files; one conftest only (C-22) |
| 5 | OWNER-GATED (Q2) | **not started — open, deferred** | — | No code until the owner answers; BLOCK 3 + 4 are its prerequisites |
| 6 | OWNER-GATED (Q1) — DEGRADED | **not started — 5 unconditional fixes pending** | — | Q8 mechanism closed; violations 1–5 + `search_vector*` ship without Q1 |
| 7 | OWNER-GATED (Q4) | **not started — open, deferred** | — | C-15 blast radius: `conftest.py` + all of `test_sweep_delete.py`; next migration `0009_*` |
| 8 | OWNER-GATED (Q5) — DEGRADED | **not started — 8A pending** | — | 8A (allow-list) ships without Q5; 8B waits |
| 9 | READY-WITH-CORRECTIONS | not started | — | Q11 closed; tripwire is phase 03's, in `test_admin_actions.py` |
| 10 | READY-WITH-CORRECTIONS | not started | — | Q9-sizing closed; blocked by `7 → 10` for the migration number |
| 11 | MOOT-SUPERSEDED | **not started — superseded** | — | `AD-012` shipped by `ba1b059`; **no second patch for one predicate** |
| 12 | READY-WITH-CORRECTIONS | not started | — | Q12 closed; reuse the existing expired string; do not absorb `OperationalError` |
| 13 | OWNER-GATED (Q6) | **not started — open, deferred** | — | `MEDIA-002` has **not** shipped; gate is live |
| 14 | READY-WITH-CORRECTIONS — RECORD-ONLY | not started | — | `db-retention.md` `AD-003` reconciliation; `AD-015` `UserAdmin` half = shipped |

### §7.1 Gate register

Recorded here so a gate is never lost between blocks.

| Gate | Block | State at plan time | Blocks if unanswered |
|---|---|---|---|
| **Q1** — admin lifecycle write seam | 6 | **OPEN — owner** | 6's read-only half only; the five unconditional fixes still ship |
| **Q2** — `ON_MODERATION` durability | 5 | **OPEN — owner** | All of BLOCK 5 |
| **Q4** — retention anchor | 7 | **OPEN — owner** | All of BLOCK 7 |
| **Q5** — failed-ad edit rule | 8 | **OPEN — owner** | BLOCK 8B only; 8A still ships |
| **Q6** — `AD-006` vs `MEDIA-002` | 13 | **OPEN — coordinator** | All of BLOCK 13 |
| **Q7** — `_pass_moderation` bare handler | 12 | **OPEN — coordinator, non-blocking** | Nothing; it only sizes BLOCK 12 |
| **Q8-value** — the audit row's placement | 6 | **OPEN** (mechanism closed) | The read-only half only |
| **Q10-value** — the replacement fixture default | 4 | **OPEN — block-internal Planner step** | Nothing; the mechanism (change the default first) proceeds |
| Q3 · Q8-mechanism · Q9-sizing · Q11 · Q12 | 2 · 6 · 10 · 9 · 12 | **CLOSED** in the source plan §0.6 | — |