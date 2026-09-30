---
plan_id: "05-ad-lifecycle-remediation"
phase: "05"
phase_name: "Ad Lifecycle, Categories & Moderation"
source_report: ".ai/audit/99-validation/05-ad-lifecycle-validated-findings.md"
source_findings: ".ai/audit/05-ad-lifecycle/findings.md"
date: "2026-09-29"
planner: "Planner (subagent)"
anchor_commit: "aa2a6b0"
report_anchor_commit: "9e96b84"
status: "planned"
findings_in_scope: 22
findings_open: 13
findings_partial: 2
findings_superseded: 2
findings_retired: 1
findings_rejected: 0
blocks: 14
---

# Execution Plan — Phase 05 Remediation (Ad Lifecycle, Categories & Moderation)

## 0. Header, provenance and scope statement

### 0.1 Provenance

| Item | Value |
|---|---|
| Source report | `.ai/audit/99-validation/05-ad-lifecycle-validated-findings.md` (validated, 783 lines) |
| Source findings file | `.ai/audit/05-ad-lifecycle/findings.md` — **deleted from the working tree** (tracked deletion). Recorded for traceability only; **not** an input, and **not** a problem to fix. No block may restore it. |
| Report anchor commit | `9e96b84` (recorded in the report metadata — **stale**) |
| Code-context document | `.ai/tmp/code-context-phase05.md` (1506 lines, Auditor) |
| **Working anchor commit for this plan** | **`aa2a6b0`** (`git rev-parse --short HEAD`) |
| Date | 2026-09-29 |
| Findings in scope | 16 `AD-*` (`AD-001` … `AD-016`) + 6 `VAL-*` (`VAL-001` … `VAL-006`) = **22** |
| Verdicts in the source report | Validated unchanged 7 · Reclassified 1 · Adjusted 6 · Merged 2 · Rejected **0** · New 1 |
| State at the anchor | 0 already fixed · **13 still open** · **2 partial** · **2 superseded** · **1 retired** · **0 rejected** |
| Execution blocks | 14 (13 with code, 1 records-only) |
| Implementor concurrency | 1, strictly sequential (project rule: only one implementor at a time) |

**Naming convention used by this plan.** This plan cites its own items with the
**cycle-scoped prefix `05-ad-lifecycle-AD-00N` / `05-VAL-00N`**, and §0.2 records why
(`VAL-001`). The convention was adopted by phase 03 (`03-DB-00N` / `03-VAL-00N`) and is
**mandatory** here: a bare `AD-001` in the tree means a *previous* cycle's finding, never
this cycle's CRITICAL. Short form `AD-00N` is used inside this document only where §0.2
`VAL-001` has just established the referent.

---

### 0.2 Evidence basis — read this before executing any block

Two inputs plus the tree. They do not fully agree with each other. **The tree at `aa2a6b0`
is the authority.** Where they disagree, the disagreement is recorded here.

#### 0.2.1 What the Planner re-verified directly in the tree at `aa2a6b0`

Every row is a read of the named `file` → `symbol`. No line number is ever used as a task
target; the line numbers below are evidence prose only.

| Claim | Verification in the tree at `aa2a6b0` |
|---|---|
| `AD-001` open | `src/backend/apps/ads/admin.py` → `class AdAdmin` sets `readonly_fields` and `actions` and nothing else — **no `fields`, no `fieldsets`, no `exclude`, no `form`, no `save_model`, no `save_formset`**. `get_form()` is Django's auto-builder, so `status`, `user`, `published_at`, `original_published_at`, `archived_at`, `deleted_at` and all four `search_vector*` columns are form-writable. The four `actions` delegate to `bulk_approve` / `bulk_reject` / `bulk_ban_users` / `bulk_delete`. |
| `AD-002` open | `src/backend/apps/ads/views/edit.py` → `ad_edit`: branch order is `is_reactivation` → `status == PUBLISHED` (with a `has_text_change` sub-branch) → **`else:` catch-all** whose `update_fields` list contains neither `status` nor `moderation_failed_at`. The catch-all is reached by `DRAFT`, `ON_MODERATION`, `ON_MODERATION_FAILED`, `REJECTED`, `DELETED`, and by `ARCHIVED` when the POST carries no `reactivate` — **five of the seven statuses**, confirmed against `ALLOWED_TRANSITIONS`. `src/backend/templates/ads/dashboard.html` renders the Edit link unconditionally. |
| `AD-003` retired | `src/backend/apps/ads/services/copy_service.py` → `copy_ad` still reuses storage keys and still documents it ("new rows, same storage keys — no file duplication"). `src/backend/apps/media/signals.py` → `delete_adimage_files_on_delete` still has **no** reference check. **Phase 07's validated report has ruled** (§0.2.2 C-4): N-references, refcount-aware free; the `pre_delete` half is absorbed into `MEDIA-001`; `copy_ad` aliasing is legal behaviour. |
| `AD-004` open | `src/backend/apps/core/management/commands/delete_sweep.py` → `Command.handle`: `cutoff_date = timezone.now() - timedelta(days=60)`, `Ad.objects.filter(status=AdStatus.ARCHIVED, archived_at__lt=cutoff_date)`, one `atomic()` + `advisory_lock(DELETE_SWEEP)`, **no `select_for_update()`**. `src/backend/apps/ads/models.py` → `Ad.Meta.indexes` declares `IX_ads_delete_sweep` on `fields=["status", "archived_at"], condition=Q(status=AdStatus.ARCHIVED)`. `docs/02-database/db-retention.md` states `ARCHIVED → 2 months (from archived_at)`. |
| `AD-005` superseded | `src/telegram_bot/services/ad_data/orm.py` → `create_draft_ad` still wraps the INSERT in the outermost `atomic()`. **Phase 03 BLOCK 4 (`03-DB-001`) owns it. Phase 05 ships nothing.** |
| `AD-006` open, contested | `src/backend/apps/ads/services/images.py` → `AdImageService.create_or_skip` filters `AdImage.objects.filter(sha256=sha256, ad__user_id=ad.user_id).first()` and returns that row — **seller-scoped, not ad-scoped** — and its own docstring says so. |
| `AD-007` superseded | `sweep_drafts.Command.handle` still filters `created_at__lt`; `IX_ads_draft_sweep` still on `["status", "created_at"]`. **Phase 03 BLOCK 6 owns it, including the seller-facing message.** |
| `AD-008` open | `src/backend/apps/ads/models.py` → `Ad.transition_to`: `ALLOWED_TRANSITIONS[ON_MODERATION] = {PUBLISHED, REJECTED, ON_MODERATION_FAILED}` and `ALLOWED_TRANSITIONS[PUBLISHED] = {ARCHIVED, ON_MODERATION}`. Both production writers — `submit_ad` (`src/backend/apps/ads/services/submission.py`) and `ad_reactivate` (`views/edit.py`) — call `transition_to(ON_MODERATION)` and then `auto_moderate()` **in the same `atomic()`**, so the state is never committed. |
| `AD-009` open, test-pinned | `views/edit.py` → `ad_edit`, the `PUBLISHED`-and-not-`has_text_change` branch saves `update_fields=["price_amount", "price_currency", "price_normalized_eur", "updated_at"]` — `published_at` absent, `transition_to` not called. **`ALLOWED_TRANSITIONS[PUBLISHED]` has no `PUBLISHED → PUBLISHED` edge**, so a naive self-transition raises `ValueError`. |
| `AD-010` open (narrow) | `src/backend/apps/moderation/views/api_bulk.py` → `bulk_moderation_action`: `BulkModerationRequest.model_validate_json`, a `MAX_BULK_ACTIONS` bound, then a loop of `Ad.objects.get(id=ad_id)` with **no `atomic()` and no `select_for_update()`**, branching on a `BulkModerationAction` `StrEnum`, delegating APPROVE/REJECT to `apps.moderation.admin_actions.approve_ad` / `reject_ad`, calling `PriorityService().calculate_and_save(ad)` outside any transaction, and ending in `except Exception` → `logger.error` + `{"id": ad_id, "error": "Processing failed"}`. |
| `AD-011` open | `models.py` → `Ad.transition_to`, the `target == AdStatus.PUBLISHED` branch sets `published_at`, sets `original_published_at` once, sets `published_by_id` when a moderator id is supplied — and nulls **neither** `archived_at` **nor** `moderated_by` **nor** `moderation_failed_at`. The branch accumulates `update_fields` incrementally, and the method begins with `self.refresh_from_db()`. |
| `AD-012` open (bot half) | `src/telegram_bot/handlers/ad_copy.py` → `cmd_copy`: `except PermissionError` then `except Exception as e:` → `_("Failed to copy ad: {error}").format(error=e)`. The interpolated value is the raw psycopg text. `_()` is applied **before** `.format`, so the whole sentence is one translated unit. |
| `AD-013` open | `models.py` → `Ad.transition_to` builds `ALLOWED_TRANSITIONS: dict[AdStatus, set[AdStatus]]` as a **function-local literal**. There is no module-level symbol; a module-scope `ALLOWED_TRANSITIONS` does not exist. |
| `AD-014` open | `models.py` → `AdImage.Meta` declares `db_table = "ad_images"`, `ordering = ["position"]`, four `CheckConstraint`s on key formats and four single-column indexes. **No `unique_together`, no `UniqueConstraint` on `(ad, position)`.** |
| `AD-015` partial | `src/backend/apps/ads/services/listings_query.py` → `ListingsQuery.build_queryset` opens with `Ad.objects.filter(status=AdStatus.PUBLISHED, user__is_declined=False)` — **no `ads_auto_publish` term**. `src/backend/apps/users/services/account_state.py` → `AccountState` carries five flags and exposes `can_publish_ad`; there is no `is_ads_visible` counterpart. `src/backend/apps/users/admin.py` → `UserAdmin` sets no `fields`/`fieldsets`/`form`. **All three halves are owned elsewhere (§5.1, §5.2).** |
| `AD-016` open (partial) | `src/backend/apps/ads/services/submission.py` → `submit_ad` returns `(False, ["Ad not found"])` on `Ad.DoesNotExist` and `(False, ["Ad failed moderation checks"])` on a moderation failure — the same shape for two different causes. `src/telegram_bot/handlers/ad_create/submit.py` → `process_preview` renders one message for every non-success and then calls `await state.clear()`. |
| `VAL-001` open | `AD-001` appears in `Ad.transition_to`'s `ON_MODERATION_FAILED` comment (`# manual review of auto-failed ads (AD-001)`) and in its `DELETED` branch (`# "last modified" timestamp (AD-001)`); `DB-003` appears in the `refresh_from_db()` comment of the **same method**. Three bare, mutually unrelated IDs inside one function. |
| `VAL-002` open, **~3× larger than reported** | `src/backend/conftest.py` → `create_test_ad` declares `status: AdStatus = AdStatus.ON_MODERATION` as its **default**; `create_test_ads_bulk` does the same. `src/telegram_bot/tests/conftest.py` redefines both for the bot package. See §0.2.3. |
| `VAL-003` open | `src/backend/apps/moderation/admin_actions.py` → `bulk_approve` filters a single status; `approve_ad` returns `False` unless the ad is in that one status; `src/backend/apps/moderation/views/review.py` → the approve view gates on `status=AdStatus.ON_MODERATION` while the detail view at the same file gates on `status__in=[ON_MODERATION, ON_MODERATION_FAILED]`, and `bulk_reject` gates on the same pair. **The approve path is the only one of the four that does not use the pair.** |
| `VAL-005` open | `docs/02-database/db-retention.md` says `ARCHIVED → 2 months (from archived_at)` and `archive_sweep → 60 days`; `docs/04-user-stories/seller-stories.md` US-S7 says *"2 months after last publish/edit → `ARCHIVED`; 4 months → permanently removed. Timers count from `published_at`"*; `docs/04-user-stories/admin-stories.md` US-A5 says *"archive @2 months, delete @4 months (from `published_at`)"*. Three documents, two anchors. |
| `VAL-006` open | `Ad.transition_to` has **two** production writers in the web/admin tier that never call it: the `AdAdmin` auto-built form and `ad_edit`'s catch-all. There is no single owner for a lifecycle-status write. |
| Migration numbering | `src/backend/apps/ads/migrations/` → `0001_initial` … `0007_adimage_ix_adimages_image_and_more`; **next is `0008_*`**. `apps/core/migrations/` → next is `0006_*`. `apps/media/migrations/` → next is `0002_*`. `apps/moderation/migrations/` → next is `0002_*`. |
| Baseline static gates | `uv run ruff check src/` → **All checks passed!**; `uv run basedpyright src/` → **0 errors, 0 warnings, 0 notes**. |

#### 0.2.2 Report / code-context statements the **tree** contradicts

| # | Statement | What the tree shows | Where this plan acts |
|---|---|---|---|
| **C-1** | The report's headline severity split is `1 CRITICAL · 4 HIGH · 8 MEDIUM · 3 LOW = 16`. | That is **14** live findings at those bands, not 16. `AD-005` and `AD-007` were merged away and carry no phase-05 severity. See §0.4. | §0.4 records the corrected tally. |
| **C-2** | The report's R-26 correction: *"12 basedpyright errors in 2 files"*. | **Superseded at `aa2a6b0`**: `uv run basedpyright src/` reports **0 errors, 0 warnings, 0 notes**. Phase 01 `ENT-004` fixed the CI gate scope to `src/`, which is what removed them. | The figure must **not** appear in any block, task YAML or commit message. §0.2.4 U15. |
| **C-3** | `VAL-002`: *"34 call sites in 10 files"*. | The 34 figure counts only `status=AdStatus.ON_MODERATION)` argument occurrences. It misses the **fixture default**: `create_test_ad`'s signature carries `status: AdStatus = AdStatus.ON_MODERATION`, and `create_test_ads_bulk` does too. Every call that omits `status=` silently fabricates the state. | BLOCK 4 re-measures and owns the real number. §0.2.3. |
| **C-4** | The report treats `AD-003` as a HIGH with a phase-05 code fix (`copy_ad`). | **Phase 07's validated report has already ruled**: the invariant is N-references with a refcount-aware free, the `pre_delete` half is **absorbed into `MEDIA-001`**, and `copy_ad` aliasing is **legal behaviour, not a bug**. It explicitly forbids shipping "copy the bytes". | `AD-003` is **RETIRED**; BLOCK 14 records the trade-off. **No block copies bytes.** |
| **C-5** | The report's `AD-011` evidence quotes a `PUBLISHED` branch that nulls `moderated_by` and `moderation_failed_at`. | The shipped branch nulls **none** of the three. The report's own AD-011 validation note already flags this; the code context repeats it. | The conclusion survives; BLOCK 1 works from the **shipped branch**, not the quote. Recorded so no implementor edits code that does not exist. |
| **C-6** | The report's `AD-010` recommendation is *"delete the loop and call `bulk_approve`/`bulk_reject`"*. | `bulk_approve`/`bulk_reject` take a **`QuerySet`**, not an id list. The endpoint already delegates to the **services** `approve_ad`/`reject_ad`. The recommendation is unexecutable and the root cause ("duplicated implementation") is refuted. | BLOCK 9 ships only what survives: transaction, row lock, error honesty. |
| **C-7** | `AD-008`'s "drop `ON_MODERATION` from the durable set" branch is offered as a remediation option. | The report itself forbids it before `VAL-003` is resolved. It would delete the queue US-A12/US-A13 and `db-enums.md` promise. | Recorded as Q2 option (iii) with its full scope cost. **This plan does not pick it.** |
| **C-8** | `AD-006` is filed MEDIUM by phase 05; `MEDIA-002` is filed **HIGH** by phase 07 for the identical predicate. | Same behaviour, two records, two ratings. Phase 07's cross-phase table states the media-side record is the higher of the two. | Q6 is a **hard gate** on BLOCK 13. §5.3. |
| **C-9** | The report attributes `AD-012`'s DB half (`uq_ads_single_draft_per_user`) to phase 05. | Already merged to `03-DB-009` by the report itself and owned by **phase 03 BLOCK 10**. | BLOCK 11 ships the CWE-209 bot half only. |

#### 0.2.3 Planner finding — `VAL-002` is the rollout-safety blocker and it is roughly three times the stated size

The report's headline for `VAL-002` is *"34 call sites in 10 files"*. The code context
re-measured it and found the number is a **floor**, because it is measured by grepping for
the *argument* `status=AdStatus.ON_MODERATION)`, which cannot see a fixture default.

The **default** parameter of `create_test_ad` in `src/backend/conftest.py` — and of
`create_test_ads_bulk`, and of both in `src/telegram_bot/tests/conftest.py` — is
`AdStatus.ON_MODERATION`. Any call that omits `status=` produces an `ON_MODERATION` row
that the production system has never produced and still cannot produce. That is a second,
silent fabrication channel with a different blast radius: the first is one keyword argument,
the second is the **absence** of a keyword argument.

**Consequence, and it is the reason BLOCK 4 exists as its own block.** A naive
remediation of `AD-008` that makes `ON_MODERATION` durable will leave roughly half of these
fabricated tests still green — they now pass against a state that has become real — so the
suite would go green while having validated **nothing** about the new durability path. The
fabrications must be migrated to reach the state through the real path, **in the same
change**, or the fix is unvalidated.

The cheapest mechanical lever is to change the fixture default first, in its own commit:
that converts the silent channel into loud failures, and the failure list *is* the
migration map. BLOCK 4 is ordered exactly that way.

The exact counts are **not** asserted by this plan — the tree drifts and another phase may
have edited the test files. BLOCK 4's Auditor step re-measures; this section records that
the reported figure is a **floor**, not a total.

#### 0.2.4 Inherited runtime claims this plan does **not** treat as proven

Nothing in the Auditor pass executed against a database: no container was started, no suite
was run, no migration applied, no admin POST issued, no Telegram update simulated. The
claims below are **inherited** from the source report or the code context. Each is listed
with what would verify it. **A block may not cite any of them as a proven precondition
without running the verification itself.**

| # | Claim | How to verify |
|---|---|---|
| U1 | An admin POST of `status=published` with a hand-picked `published_at` returns **302** and commits with `ModeratorActionLog == 0`, `AnalyticsEvent == 0`, the ad in the public queryset. | Admin-client POST against the Docker test DB with a staff user; assert all three counts and membership in `ListingsQuery.build_queryset(...)`. |
| U2 | `status=REJECTED` and `status=ON_MODERATION_FAILED` return **HTTP 500** with a `CheckViolation`, not a form error. | Same POST; assert the status code and the raised `IntegrityError`. **Statically predicted** by `readonly_fields` omitting the required timestamps; the HTTP status is a runtime fact. |
| U3 | `DELETED → published` through the form succeeds (terminal-state resurrection). | Same POST on a `DELETED` row. |
| U4 | Zero rows are ever committed in `ON_MODERATION`; `get_pending_queue_size() == 0`. | Run a real `submit_ad` in the test DB and count. **Statically re-derivable**; the empirical count is a runtime fact. |
| U5 | `bulk_approve` returns **0**, the approve view **404s**, `approve_ad` returns `False` for every real ad. | Test client against the test DB. **Statically re-derivable** from the three single-status filters; independently reproduced by phase 15's validator. |
| U6 | `copy_ad` yields byte-identical storage keys and deleting the source leaves the copy with absent files. | **Do not spend a test on it** — superseded by `MEDIA-001` (C-4). |
| U7 | `create_or_skip(ad=adA, image=<key already on adB>)` returns adB's row and adA ends with 0 photos. | A unit test under the existing `isolated_media_root` fixture. Cheap; this is BLOCK 13's regression test — **subject to the Q6 gate**. |
| U8 | `copy_ad` with an open `DRAFT` raises `IntegrityError` naming `uq_ads_single_draft_per_user`. | A test that opens a `DRAFT` for the seller, then calls `copy_ad`. |
| U9 | A fresh manual archive back-dated 61 days **is** selected by `delete_sweep` today. | A `delete_sweep` test with a back-dated row. The predicate half is statically obvious; the target behaviour is **Q4**, not a fact. |
| U10 | A price-only edit leaves `published_at` unchanged. | **Already pinned by a shipped test** (`test_edit_published_price_only_stays_published`). Not re-run. |
| U11 | The `ON_MODERATION_FAILED` edit returns **200**, rewrites `title`, leaves `status` and `moderation_failed_at` untouched, and the purge reclaims it. | A test in `apps/ads/tests/test_edit.py`. **Statically predicted** by the catch-all's `update_fields` list. |
| U12 | Duplicate `(ad, position)` rows exist in a real database. | **Not asked and not answered.** Q9. Must be run against a production-shaped dataset before `AD-014`'s migration. |
| U13 | Promoting media before the transaction commits leaves unreferenced permanent files after a rollback. | **Phase 03 BLOCK 8's**, not phase 05's. Its test class docstring currently documents the behaviour as intended and must change with the code. |
| U14 | The exact exception class the outermost-`atomic()` `IntegrityError` recovery raises. | **Phase 03 BLOCK 4's.** Django's `needs_rollback` is unambiguous statically; the class name is a runtime detail. |
| U15 | *"12 basedpyright errors in 2 files."* | **Superseded at the anchor**: 0 errors. See C-2. |
| U16 | Whether `apps/ads/services/edit.py` exists (phase 04's §0.2 cites it). | **Resolved statically: it does not.** `apps/ads/services/` holds only `copy_service.py`, `favorites.py`, `images.py`, `listings_query.py`, `submission.py`. All edit logic is in `apps/ads/views/edit.py`. |
| U17 | Whether `ALLOWED_TRANSITIONS` is reachable at module scope. | **Resolved statically: it is not** — it is a local name inside `Ad.transition_to`'s body. This is `AD-013`'s premise. |
| U18 | Whether `AdImage` declares `unique_together` / a `(ad, position)` constraint. | **Resolved by reading `AdImage.Meta`**: neither exists. |

---

### 0.3 Scope statement (explicit)

**In scope — implemented by this plan (12):**
`05-ad-lifecycle-AD-001` (BLOCK 6), `-002` (BLOCK 8), `-004` (BLOCK 7), `-006`
(BLOCK 13), `-008` (BLOCK 5), `-009` (BLOCK 2), `-010` (BLOCK 9), `-011` (BLOCK 1),
`-012` (bot half, BLOCK 11), `-013` (BLOCK 1), `-014` (BLOCK 10), `-016` (BLOCK 12).
Plus `05-VAL-002` (BLOCK 4), `05-VAL-003` (BLOCK 3) and the BLOCK 1 half of `05-VAL-001`.

**Partial — one half shipped here, the rest owned elsewhere (2):**

- **`05-AD-012`** — the **CWE-209 bot half only** (`cmd_copy` renders raw driver text). The
  single-`DRAFT`-invariant half is `03-DB-009` (phase 03 BLOCK 10).
- **`05-AD-016`** — the **distinguishable return + non-destructive FSM half only**. The
  sweep predicate, the `ads/0008_*` migration and the seller-facing "your draft expired"
  message are `03-DB-003` (phase 03 BLOCK 6). **One message per condition** (§5.3).

**Retired — no code change (1):**

- **`05-AD-003`** — **retired by phase 07's decision** (C-4). The data-loss half is absorbed
  into `07-MEDIA-001`; `copy_ad`'s key reuse is legal under the refcount model. **Phase 05
  must not implement the byte-copy branch.** The residue is documentation, in BLOCK 14.

**Superseded — shipped by phase 03, phase 05 ships nothing (2):**

- **`05-AD-005`** → `03-DB-001` (phase 03 BLOCK 4). Confirmed still open in the tree, for
  the record; **no second patch**.
- **`05-AD-007`** → `03-DB-003` (phase 03 BLOCK 6), which also carries the seller-facing
  message.

**Reserved to other phases — recorded, not fixed (1):**

- **`05-AD-015`** — the `UserAdmin` exposure half is **phase 04 BLOCK 1**; the
  queryset-level visibility predicate is **phase 06 `PII-104` + `VAL-003`** and **phase 15
  `AUTHZ-005`**. **No phase-05 block may add `is_ads_visible` to `AccountState`** — that
  would create the second ad-hoc predicate those findings exist to prevent. BLOCK 14 records
  the defect so the final report does not read as an open unowned finding. (§5.1, §5.2)

**Landed as binding constraints or records, not as separate code (6 `VAL-`):**

- **`05-VAL-001`** — the **tracker convention** is **decided** (cycle-scoped IDs, §0.1) and
  is binding on every block. The **disambiguation of the three bare IDs inside
  `Ad.transition_to`** is a named deliverable of BLOCK 1, which rewrites exactly those
  lines. The ~68-citation repository sweep is **phase 03 BLOCK 11's** and phase 05 must not
  start it.
- **`05-VAL-002`** — BLOCK 4, and the hard ordering edge `4 → 5`.
- **`05-VAL-003`** — BLOCK 3, and the hard ordering edge `3 → 6`.
- **`05-VAL-004`** — **resolved** by phase 07. No phase-05 decision. (§0.2.2 C-4)
- **`05-VAL-005`** — the owner decision is **Q4** and is a **hard gate on BLOCK 7**; BLOCK 2
  must not assume the anchor either way.
- **`05-VAL-006`** — the owner decision is **Q1** and is a **hard gate on BLOCK 6**; BLOCK 8
  must not pre-empt it.

**Counts:** 12 implemented + 2 partial + 1 retired + 2 superseded + 1 reserved + 6 `VAL-`
(recorded) = **22** items, **14** blocks.

---

### 0.4 Severity corrections

**The report's headline tally is arithmetically wrong and is corrected here.** The report
states `1 CRITICAL · 4 HIGH · 8 MEDIUM · 3 LOW = 16` and simultaneously states that
`AD-005` and `AD-007` were merged away and "carries no phase-05 severity". The report's own
per-finding verdict table assigns severities to **14** surviving findings, not 16.

| Band | Report headline | **Corrected at `aa2a6b0`** | Findings |
|---|---|---|---|
| CRITICAL | 1 | **1** | `05-AD-001` |
| HIGH | 4 | **3 → 2 after phase 07** | `05-AD-002`, `05-AD-004`; `05-AD-003` is **retired** (C-4), so its HIGH is withdrawn from the phase-05 tally |
| MEDIUM | 8 | **7** | `05-AD-006`, `-008`, `-009`, `-010`, `-011`, `-012`, `-016` |
| LOW | 3 | **3** | `05-AD-013`, `-014`, `-015` |
| **live total** | 16 | **14** | — |

**No live finding moves band.** Two further corrections apply to the process, not to a
finding's severity:

1. **The static-gate baseline is green, not "12 errors".** Phase 01 `ENT-004` fixed the CI
   gate scope to `src/`, which is what removed the report's 12 test-only type errors.
   `uv run basedpyright src/` reports **0 errors** at the anchor (C-2, U15). Any block that
   cites the "12 errors" figure is wrong and its citation must be removed.
2. **`AD-005` was filed HIGH by phase 05 and MEDIUM by phase 03 (`03-DB-001`) for the same
   defect.** Phase 03 already escalated this as `03-VAL-003` and recorded that **one** work
   item ships at MEDIUM. **Phase 05 does not re-rate it and does not ship a second patch**
   (§5.2). The discrepancy is noted here only so the final report does not present a
   CRITICAL/HIGH pair for a defect that destroys no data.

**Severity is not execution order.** BLOCK 3 is `VAL-003` (HIGH) and lands before BLOCK 6
(`AD-001`, CRITICAL) — not because it is more severe, but because BLOCK 6 is unsafe without
it (§4.2).

---

### 0.5 Open technical questions — resolved here, or explicitly gated in their block

The code context raises **12** questions. **Nothing below is left silently ambiguous.** Each
is either DECIDED here, with the reasoning stated, or carries a labelled
**decision gate** inside its block with the options and their consequences recorded. **This
plan does not choose on any question where the code context flagged real uncertainty**, and
it does not choose either of the two questions that are not the implementor's to answer.

| # | Question | Disposition | Owner | Gate |
|---|---|---|---|---|
| **Q1** | May a moderator move an ad's status, and through which single write path? | **OPEN — owner decision.** Gating `AD-001`, and via `VAL-006` also `AD-008`, `AD-010`, `AD-011`, `VAL-003`. Nothing in `docs/` says whether the admin change form is a supported surface. | **User / product, via the coordinator** | Hard gate on **BLOCK 6**. Not an investigation. |
| **Q2** | Which side of `ON_MODERATION` durability does the business want? | **OPEN — product decision.** Gating `AD-008` and constraining `VAL-003`'s final shape. | **User / product, via the coordinator** | Hard gate on **BLOCK 5**. **BLOCK 3 is deliberately built to be valid under all three answers** (§3.3.1). |
| **Q3** | `AD-009`: a `PUBLISHED → PUBLISHED` matrix self-edge, or an explicit timer-bump service? | **OPEN — decision gate.** Genuinely two shapes with different costs. | Researcher + Planner | Inside **BLOCK 2** |
| **Q4** | `AD-004`: predicate change, index change, or both — and is the retention anchor a code change or a documentation change? | **OPEN — owner + technical.** Gating `AD-004`. `db-retention.md`, US-S7 and US-A5 disagree about the anchor. | **Owner** (anchor) + Researcher + Planner (shape) | Hard gate on **BLOCK 7** |
| **Q5** | `AD-002`: what is the product rule for editing a failed ad? | **OPEN — product decision.** Gating `AD-002`. Options (a) and (c) hide the dead end without resetting the purge timer. | **User / product, via the coordinator** | Hard gate on **BLOCK 8** |
| **Q6** | Which of `AD-006` and `MEDIA-002` is the record? | **OPEN — owner decision.** Same predicate, two records, two ratings (MEDIUM vs HIGH). | **Coordinator** | Hard gate on **BLOCK 13** |
| **Q7** | Is `auto_moderate`'s bare `except Exception` in `_pass_moderation` (which converts a system error into a content verdict for the seller) a phase-05 finding? | **OPEN — scope decision, not a blocker.** The code context raises it and states it is **not** in the report's scope. | **Coordinator** | Inside **BLOCK 12**, non-blocking: BLOCK 12 ships either way; Q7 only decides whether one extra branch is added. |
| **Q8** | Where does the `AdAdmin` audit row go, and with which `ModeratorActionType`? | **OPEN — technical, a sub-question of Q1(b).** `moderation_log.set_published` already writes `log_manual_publish` when a `moderator_id` is supplied, but `transition_to` returns `None`, so the form's save path must learn the previous status somehow. | Researcher + Planner | Inside **BLOCK 6** |
| **Q9** | `AD-014`: do duplicate `(ad, position)` rows already exist? | **OPEN — data fact.** Cannot be answered without running a query against a production-shaped dataset. `AddConstraint` fails if they do. | Auditor (BLOCK 10 pre-flight) | Hard gate on **BLOCK 10**'s migration |
| **Q10** | `VAL-002`: may the migration start by changing `create_test_ad`'s default status, and to which replacement status? | **DECIDED (mechanism) / OPEN (value).** The *mechanism* — change the default first, in its own commit, so the silent channel becomes loud failures — is the correct forcing function and the failure list is the migration map. The *value* must be chosen by the block's Planner step, because it trades unrelated breakage against clarity. | Planner, BLOCK 4 | Inside **BLOCK 4** |
| **Q11** | `AD-010`: per-ad transaction, per-request transaction, or a bulk `QuerySet` rewrite — and what may the returned `error` string say? | **OPEN — decision gate.** A per-request `atomic()` contradicts the endpoint's own `{"completed": N, "errors": [...]}` partial-failure shape. The error string is operator-facing on an HTTP 200 and must be actionable without leaking internals. | Researcher + Planner | Inside **BLOCK 9** |
| **Q12** | `AD-016`: what does "distinguishable" mean in `submit_ad`'s `tuple[bool, list[str]]` return? | **OPEN — decision gate.** A sentinel string is fragile; a richer return type breaks all three callers. Note `ad_edit`'s reactivation and text branches already render `errors[0]`, so they already consume it — the bot does not. | Researcher + Planner | Inside **BLOCK 12** |

**Question numbering note.** The user's summary lists "Q1 moderator-may-change-status
ownership · Q2 which side of `ON_MODERATION` durability · Q4 the retention anchor · Q5 the
failed-ad edit rule · Q6 which record owns `AD-006` vs `MEDIA-002` · Q9 whether duplicate
`(ad, position)` rows exist". Those map exactly onto the code context's Q1, Q2, Q4, Q5, Q6
and Q9 above. **All six stay open and are all gated** — none is decided by this plan.

---

## 1. Environment and command contract for the implementor

These constraints bind **every** block. They are not optional and they are not re-derived
per block.

| Concern | Rule |
|---|---|
| **Test execution** | **Docker only.** There is no database on `localhost:5432`; a host `uv run pytest` **fails** and its failure must never be reported as a test result. |
| **Test command (the default gate)** | `docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm --env PYTEST_SKIP_MARKERS=seed test` — abbreviated below as `$dc run --rm --env PYTEST_SKIP_MARKERS=seed test`. `--project-name mko-bazuna-test` and `--env-file .env.test` are **both required**; omitting the env file aborts with *"must be set"*. **Never** `mko-bazuna-dev`. |
| **Targeted run** | Same command plus `-e PYTEST_OPTS="<tokens>"`. **`PYTEST_OPTS` is word-split on spaces and unquoted** in the entrypoint: `-k test_name` and bare file paths work; a quoted multi-token value such as `-k "a b"` does **not**. |
| **`PYTEST_OPTS` side effect** | Setting it **replaces** the defaults (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`), so a targeted run loses xdist parallelism **and** `--reuse-db`. Prefer `PYTEST_SKIP_MARKERS` over `PYTEST_OPTS`. |
| **Never** | `--override-ini=addopts=` — it strips `--import-mode=importlib`, which `pyproject.toml` sets and the suite depends on. |
| **Fresh schema** | `.\Makefile.ps1 test-recreate` (`--create-db`) is **required** after **any** migration change and after an interrupted run. **Mandatory after BLOCK 7 (`ads/0008_*`), BLOCK 10 (`ads/0009_*` or later), and BLOCK 5 (if it changes schema — it must not).** |
| **Live database inspection** | BLOCK 4 (fabrication census), BLOCK 7 (predicate/`EXPLAIN`), BLOCK 9 (lock behaviour) and **BLOCK 10 (the Q9 duplicate-position pre-flight)** need real query output. Run it against the **test** database through the `test` service, never against an operator database. Never `DROP` anything outside the test stack. |
| **Static gates** | `uv run ruff check <path>` and `uv run basedpyright <path>`, and the full `uv run ruff check src/` + `uv run basedpyright src/` before every block's commit. **Both are green at `aa2a6b0` and must stay green.** The CI scope is `src/`, not `.`. |
| **`ruff` autofix** | `uv run ruff check --fix src/` sorts imports (`I001`). `ruff format` is **not** the project convention. |
| **Image rebuild** | Not needed — the `test` service bind-mounts the repository. |
| **Language** | **English only.** Comments, docstrings, log messages, error messages and documentation. |
| **`print()`** | Forbidden. `logger = logging.getLogger(__name__)` with lazy `%s` formatting. |
| **Stack (do not change)** | Django 5.2 LTS (`>=5.2.16,<6.0`) · Python 3.14 · PostgreSQL 18 · aiogram 3.x · native PostgreSQL FTS. Two processes, one DB: **web** (gunicorn sync WSGI, HTMX MPA) + **bot** (aiogram with `django.setup()`, shared ORM). **Migrations run exactly once before both start.** The bot FSM persists the ad dialog as an **`Ad` row in `DRAFT`** via the ORM. |
| **Pydantic v2** | **Only** at system boundaries — bot input DTOs (`SubmitAdInput`, `AdEditInput`, `BulkModerationRequest`), settings schemas. The Django ORM remains the persistence layer for all CRUD. No block may introduce a Pydantic model inside a service. |
| **StrEnum** | Every fixed value is an enum member, never a bare string or a dict-of-strings. The transition matrix, the retention windows and any new status set belong in `apps/core/enums.py` or `apps/ads/models.py` as module-level values (project rule 10). |
| **Service boundaries** | New business logic goes in a `services/` module, **never** in a view, a handler or a `ModelAdmin` method body. `apps.*` must **never** import `telegram_bot.*`. |
| **Bot async** | Every bot DB call is `@sync_to_async` at the default `thread_sensitive=True`. Do not "fix" a lock wait by raising the asgiref worker count. |
| **TX-then-FS** | Filesystem side effects happen only **after** commit, via `transaction.on_commit()`. Never unlink or move inside `transaction.atomic()`. |
| **Typing** | `# pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped` is the project's established, greppable inline suppression and is required on every `with transaction.atomic():` line. Never a bare suppression. |
| **i18n** | Every **user-visible** string is wrapped in `gettext`/`_()` and has a **non-empty `msgstr` for `ru` *and* `bs`** (`en` may be empty — the msgid is English). **BLOCKs 8, 11 and 12 add user-visible strings.** Gated by `test_i18n_completeness.py` and `test_i18n_pipeline.py`. `src/backend/locale/*/LC_MESSAGES/django.po` is a **shared artefact** (§5.3). |
| **Task targets** | **Never a line number.** Targets are `file` + `type` (`module` / `class` / `function` / `method`) + `name`, plus `semantic_anchors`. Line numbers may appear in evidence prose; they may **never** be a task target. |
| **Task shape** | Every block's task is written to `.ai\tasks\templates\task_template.yaml`: `targets` with `type`/`name`, `semantic_anchors`, `changes`, `acceptance_criteria`, `source_reference` / `source_section`. **Tests must verify logic and component interaction** — not a variable's absence, not a log string, not a line count. |
| **Schema changes** | **Django migrations only** (project rule 13). No hand-written DDL, no `SET CONSTRAINTS` outside a migration, no editing of a **shipped** migration. |
| **Dirty tree** | **Hard rule.** The tree is dirty **by design** and drifted during the audit pass. Never `git add -A`, `git add .`, `git commit -a`, `git reset`, `git checkout`, `git stash` or `git clean`. Stage explicit paths (`git add <specific-files>`) and re-read `git status --short` **immediately before every commit**. Changes you did not make are normal — other agents commit concurrently; do not revert them. |
| **Audit tree** | `.ai/audit/**` is **unmodifiable**. No block may edit, restore or re-create any file under it, including the 19 currently-tracked deletions. |
| **Commits** | One block = one commit, staged by explicit path, message `"{type}({scope}): {description}"` in the repository's style (`fix(...)`, `test(...)`, `docs(...)`, `refactor(...)`). **Never rewrite history.** Do not commit without an explicit user request. |
| **Implementor concurrency** | **Exactly one Implementor at a time, strictly sequential.** Auditor / Researcher / Planner / Validator run as analysis or review passes inside a block. |
| **Production code is king** | If a shipped **green** test conflicts with architecture or business logic, **fix the test, not the code**, and record the justification in the commit message. **Two tests are named for rewrite in this plan** — `test_edit_published_price_only_stays_published` (BLOCK 2) and `test_edit_on_moderation_direct_save` (BLOCK 8) — plus the implicit-`status` call sites BLOCK 4 must triage. |
| **Documentation** | Docs in `docs/` stay in sync with the code they describe. BLOCKs 2, 5, 7, 8, 10 and 14 have DOC-UPDATE deliverables. **`docs/01-spec/technical-specification.md` is being edited by phase 06 (`PII-113`) — no block may edit it** (§5.2). |
| **PowerShell** | `head` and `tail` do not work. Use `Select-Object -First/-Last`, `Get-Content -TotalCount`, `Select-String`. |

---

## 2. Scope decisions table (acceptance contract for execution)

| ID | Disposition | Block | Final severity | One-line reason |
|---|---|---|---|---|
| `05-AD-001` | **implement** — gated on **Q1**; must land **after** `VAL-003` | BLOCK 6 | **CRITICAL** | The form writes lifecycle state with no audit row, rewrites `original_published_at`, reassigns the owner and 500s on two statuses. It is not a patch: it needs one sanctioned write path **and** an owner decision. |
| `05-AD-002` | **implement** — gated on **Q5**; scope is **five** statuses, not two | BLOCK 8 | HIGH | Content is rewritten while `moderation_failed_at` is untouched, so the purge reclaims the work. The structural fix is an allow-list plus a state owner, not another branch. |
| `05-AD-003` | **retired — no code change** | BLOCK 14 (record only) | HIGH (withdrawn) | Phase 07 ruled: N-references with a refcount-aware free; aliasing is legal. **Phase 05 must not copy the bytes.** |
| `05-AD-004` | **implement** — gated on **Q4**; **new partial index is a prerequisite, not an optimisation** | BLOCK 7 | HIGH | Re-keying the sweep on `published_at` silently drops `IX_ads_delete_sweep`. Three authoritative documents disagree about the anchor, so "correct" is undefined until the owner picks one. |
| `05-AD-005` | **superseded — no work item** | — | — | The same defect as `03-DB-001` (phase 03 BLOCK 4). Shipping both is two patches for one line. |
| `05-AD-006` | **implement, gated on Q6** — otherwise a cross-reference to `MEDIA-002` | BLOCK 13 | MEDIUM (phase 07 rates the same behaviour **HIGH**) | The dedup is seller-scoped, so a byte-identical file on a second ad returns the **first** ad's row and the second ad silently loses its photo. |
| `05-AD-007` | **superseded — no work item** | — | — | The sweep half duplicates `03-DB-003` (phase 03 BLOCK 6), which also owns the seller-facing message. |
| `05-AD-008` | **implement** — gated on **Q2**; **VAL-002 is a hard prerequisite** | BLOCK 5 | MEDIUM | `ON_MODERATION` is never committed, so the whole human-approval path is dead. This is a **spec** deviation (US-S2, US-A12, US-A13, `db-enums.md`, decision Q), not a tidiness issue. |
| `05-AD-009` | **implement** — gated on **Q3**; lands **with** `AD-013` | BLOCK 2 | MEDIUM | A price-only edit does not reset the auto-archive clock, contradicting `db-schema.md` and decision J. The naive fix raises `ValueError` — there is no `PUBLISHED → PUBLISHED` edge. |
| `05-AD-010` | **implement (narrow)** — transaction + row lock + honest error; gated on **Q11** | BLOCK 9 | MEDIUM | The report's root cause and recommendation are refuted. What survives: no transaction, no lock, and a bare `except Exception` that turns the state machine's own `ValueError` into a cause-free HTTP 200. |
| `05-AD-011` | **implement** — model-only; lands with `AD-013` | BLOCK 1 | MEDIUM | `archived_at` is genuinely never cleared on `ARCHIVED → PUBLISHED`; the one-way constraints accept the inconsistency. |
| `05-AD-012` | **implement, bot half only** — the DB half is `03-DB-009` | BLOCK 11 | MEDIUM | A psycopg `IntegrityError` — table, constraint, key detail — is formatted into a seller's Telegram chat. **CWE-209.** |
| `05-AD-013` | **implement** — zero-behaviour-change extraction; a **prerequisite** for `AD-009` | BLOCK 1 | LOW | The matrix is a function-local literal rebuilt on every call. Project rule 10 asks for it to be a named value, and `AD-009` needs somewhere to put a new edge. |
| `05-AD-014` | **implement** — gated on **Q9** (data pre-flight) | BLOCK 10 | LOW | No `(ad, position)` uniqueness. Uniqueness-only: gaps are already a **shipped, asserted** behaviour (`[0, 2, 5]`). |
| `05-AD-015` | **reserved to other phases — recorded, not fixed** | BLOCK 14 (record only) | LOW | Every half is owned elsewhere. Adding `is_ads_visible` here would create the second ad-hoc predicate that phase 06's `VAL-003` exists to prevent. |
| `05-AD-016` | **implement, two halves** — gated on **Q12**; the sweep half is `03-DB-003` | BLOCK 12 | MEDIUM | An expired draft is reported as a moderation failure and then the FSM state is cleared, so the seller cannot retry. |
| `05-VAL-001` | **split** — convention **decided**; disambiguation inside `Ad.transition_to` is **BLOCK 1**; the repository sweep is phase 03's | BLOCK 1 + plan-wide + BLOCK 14 | HIGH (tracker integrity) | `AD-001`, `AD-002`, `AD-005` and `DB-003` all appear as bare IDs in shipped source and docs, describing **earlier** cycles. An implementor grepping `AD-001` in `models.py` finds a matrix-edge comment. |
| `05-VAL-002` | **binding constraint + a first-class block** — the `4 → 5` edge is **hard** | BLOCK 4 | HIGH (rollout) | A durable `ON_MODERATION` would leave fabricated tests green, validating nothing. The fixture's **default** status is a second, silent fabrication channel the report's grep cannot see (§0.2.3). |
| `05-VAL-003` | **binding constraint** — BLOCK 3 must land before BLOCK 6 | BLOCK 3 | HIGH (rollout) | `bulk_approve` returns 0 and the approve view 404s for every real ad, so `status` → read-only would leave moderators with **no** working publish path. |
| `05-VAL-004` | **resolved by phase 07** — no phase-05 decision | — | MEDIUM | The question phase 05 asked phase 07 has been answered: N references, refcount-aware free. |
| `05-VAL-005` | **binding constraint** — the owner decision is **Q4**, a hard gate on BLOCK 7; BLOCK 2 must not assume the anchor | BLOCK 7 (+ BLOCK 2 constraint) | MEDIUM | Three findings anchor a timer to the event that *created* a state rather than the one that made the seller care, and the documents disagree about where the truth lives. |
| `05-VAL-006` | **binding constraint** — the owner decision is **Q1**, a hard gate on BLOCK 6; BLOCK 8 must not pre-empt it | BLOCK 6 (+ BLOCK 8 constraint) | MEDIUM | `AD-001`, `AD-008`, `AD-010`, `AD-011` and `VAL-003` are symptoms of one missing thing: a single owner for a lifecycle-status write. |

---

## 3. Execution blocks

Roster legend and the standing rule: **Implementor is always required, exactly one at a
time, sequentially.** Auditor / Researcher / Planner / Validator are added per block with an
explicit justification *and* an explicit statement of who is **not** required and why. The
rule "high risk ⇒ all four" is applied to **BLOCK 2, 3, 5, 6, 7, 8, 12 and 13** — see each
block for the specific reason.

**Two kinds of gate appear below, and they are not the same thing:**

- A **decision gate** is owned by the Researcher/Planner *inside* the block. It must be
  closed, and the decision recorded in the block's commit message, **before implementation
  starts**.
- An **owner gate** (Q1, Q2, Q4, Q5, Q6) is a product decision routed through the
  coordinator. **It is not an investigation and it cannot be closed by any agent in this
  plan.** A block with an owner gate may do its pre-block analysis but **must not write the
  code** until the answer is recorded.

Every block's task YAML is written to `.ai\tasks\templates\task_template.yaml` and carries
`source_reference: .ai\plans\05-ad-lifecycle-remediation.md` and `source_section: "BLOCK N
— <title>"`. **No target is a line number.**

---

### BLOCK 1 — Hoist the transition matrix, and make timestamp clearing uniform (AD-013, AD-011, VAL-001 part)

| | |
|---|---|
| **Findings owned** | `05-AD-013`, `05-AD-011`, and the `Ad.transition_to` half of `05-VAL-001` |
| **`depends_on`** | — |
| **Priority** | P0 (everything downstream depends on the matrix being inspectable) |
| **Roster** | **Implementor, Auditor, Validator** → *not* all five |

**Grouping decision.** `AD-013` is a pure extraction and `AD-011` is a one-branch behaviour
change. They are one block because they are **the same edit surface** — the body of
`Ad.transition_to` — and because `AD-009` (BLOCK 2) needs both: it must add a matrix edge
(only possible once the matrix is a named value) and it must not add a *third* divergent
timestamp-clearing idiom (which is exactly what an inconsistent `update_fields` list
invites). Three reviews of one function body would cost more than one review of two
coherent changes.

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — yes.** Must re-derive every caller of `transition_to` at the anchor and confirm
  none depends on the matrix being a local (e.g. via `inspect.getsource`), and must confirm
  no other module defines a competing transition map. Cheap, and it is the only way the
  extraction is provably behaviour-preserving.
- **Researcher — no.** There is no modern-practice or multi-approach question here. Project
  rule 10 already names the shape ("fixed value sets belong in models"), and the tree
  already shows the model. A Researcher pass would add latency and no information.
- **Planner — no.** The design is fully determined by the finding: extract verbatim, add
  one field to one branch, add it to one `update_fields` list. There is nothing to design.
- **Validator — yes.** A refactor's entire risk is *behaviour change you did not intend*.
  An independent review of the extracted matrix against the original literal, character for
  character, is the only real control.

**Findings and notes carried forward.**

1. **The extraction must be character-for-character identical.** Re-read the literal inside
   `Ad.transition_to`'s body, move it to module scope in `apps/ads/models.py` **above** the
   class, and change the method to read the module value. Do **not** "improve" it while
   moving it — no new edges, no reordered keys, no converted `set()` to `frozenset()`
   without saying so in the commit message. `AD-013` is a **zero-behaviour-change** block
   and every existing matrix test must pass **untouched**.
2. **The two special cases are not in the matrix and must stay outside it.** `DELETED → *`
   raises a `ValueError` before the matrix is consulted, and `* → DELETED` short-circuits
   *past* the matrix entirely (it sets `deleted_at` **and** `updated_at`). If either is
   folded into the extracted dict, `AD-013` stops being a refactor.
3. **The type annotation moves with it.** `dict[AdStatus, set[AdStatus]]` must be declared
   on the module-level value. `AdStatus` is already imported by `apps/ads/models.py`.
4. **`AD-011`'s fix is one assignment plus one `update_fields` entry.** In the
   `target == AdStatus.PUBLISHED` branch, add `self.archived_at = None` and append
   `"archived_at"` to the `update_fields` list that branch already accumulates. The list is
   built incrementally, so an assignment without the `update_fields` append is a **silent
   no-op** — the single most likely way this block ships broken while looking correct.
5. **Why only `ARCHIVED → PUBLISHED` is affected.** The `ON_MODERATION` branch already
   nulls `archived_at`, so `ARCHIVED → ON_MODERATION` is already correct. Only the
   `PUBLISHED` target misses it. Do not "unify" the branches — that is a design change
   beyond the finding, and `VAL-006`'s write-path decision is where that belongs.
6. **`refresh_from_db()` is the first statement of the method and is load-bearing.** It
   defeats stale-state races and raises `Ad.DoesNotExist` if a sweep hard-deleted the row
   mid-flight. Nothing in this block may move it.
7. **The three bare audit IDs in this function are part of the deliverable** (`VAL-001`).
   `Ad.transition_to` currently contains `# manual review of auto-failed ads (AD-001)` on the
   `ON_MODERATION_FAILED` edge, `# "last modified" timestamp (AD-001)` on the `DELETED`
   branch, and `# DB-003: re-read from DB …` on `refresh_from_db()`. All three are
   **previous cycles'** findings. Rewriting them to their descriptive form (phase 03 BLOCK
   11 Option C shape: say what the code does, attribute nothing uncertain) is a **named
   deliverable** of this block, because this block already rewrites exactly these lines. Do
   **not** sweep any other file — that is phase 03 BLOCK 11's (§5.2).
8. **Zero observable harm today is verified, not assumed.** Only `delete_sweep` reads
   `archived_at`, and it filters `status = ARCHIVED` as well. So the fix is correct and
   invisible — which means **only a test can catch a regression here**, and the
   bidirectional constraint test below is mandatory, not optional.

**File surface (semantic units).**
- `src/backend/apps/ads/models.py` → `Ad.transition_to` (the matrix literal, the
  `PUBLISHED` branch, the `update_fields` accumulation, the three audit-ID comments) and
  the **new module-level** `ALLOWED_TRANSITIONS` value declared above `class Ad`.
- `src/backend/apps/ads/tests/test_ad_constraints.py` → `class TestStatusTimestampConstraints`
  (extend with the bidirectional case).

**Tests required.**
- *Must be added:* in `test_ad_constraints.py::TestStatusTimestampConstraints`, a case
  asserting that a row in a non-`ARCHIVED` status carrying a stale `archived_at` is
  **rejected** by the database. This is the direct guard for `AD-011`'s round trip:
  `ARCHIVED` → `PUBLISHED` must leave `archived_at is None` **on the instance and in the
  database**, verified with a fresh `refresh_from_db()` (not by re-reading the in-memory
  object, which would pass even if `update_fields` were wrong — see note 4).
- *Must be added:* a matrix-identity test asserting the module-level `ALLOWED_TRANSITIONS`
  is importable from `apps.ads.models` and that its seven source keys and their target sets
  match the shipped matrix exactly. This is the only control that the extraction did not
  silently alter an edge.
- *Must keep passing unchanged:* `apps/ads/tests/test_ad_lifecycle.py` →
  `TestTransitionValidation`, `TestTransitionMatrixEdges`,
  `TestOriginalPublishedAtImmutability` (both cases), `TestPublishedAtUpdates::test_published_at_updates_on_re_publish`;
  `test_ad_constraints.py::TestMutualExclusivityConstraint` and the existing four
  parametrized one-way cases; `apps/ads/tests/test_transition_concurrency.py` in full.
- *Explicitly **not** to change:* `test_published_at_updates_on_re_publish` asserts nothing
  about `archived_at`, so it passes either way. Leave it alone.
- *Gate:*
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/ src/telegram_bot/tests/test_ad_lifecycle.py" test`,
  then `.\Makefile.ps1 test`, then `uv run ruff check src/` and `uv run basedpyright src/`.

**Risk / rollback.**
- *Risk:* a missed `update_fields` append makes the fix a silent no-op. *Mitigation:*
  the mandatory test asserts on a **reloaded** instance.
- *Risk:* the extraction is not verbatim, so one edge silently changes. *Mitigation:* the
  matrix-identity test.
- *Risk:* the audit-ID comment rewrite is read as "starting the §68 sweep". *Mitigation:*
  the file surface is bounded to this one function; §5.2 states the boundary.
- *Rollback:* trivial — one file, no migration, no data. Revert the commit.

---

### BLOCK 2 — A price or photo edit must restart the publish clock (AD-009, Q3)

| | |
|---|---|
| **Findings owned** | `05-AD-009`; inherits `VAL-005`'s constraint that the anchor is undecided |
| **`depends_on`** | **BLOCK 1** (hard) — the matrix must be a named value before an edge can be added to it |
| **Priority** | P1 |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- **Implementor — yes.** Always.
- **Auditor — yes.** Must re-derive the `PUBLISHED`-and-not-`has_text_change` branch in
  `ad_edit` at the anchor, confirm `published_at` is absent from its `update_fields` list,
  and confirm no **other** path bumps `published_at` on a price edit (a second writer would
  make the fix ambiguous).
- **Researcher — yes.** Q3 is a genuine two-shape question with different costs on future
  evolution, and the code context flags it as one. See the table below.
- **Planner — yes.** The block changes the state machine's public edge set, adds a
  transition self-edge whose `update_fields` semantics must be specified, and **rewrites a
  shipped green test**. That is detailed pre-implementation design.
- **Validator — yes.** MEDIUM severity, but the change silently alters a **retention
  clock**. A wrong choice either auto-archives an ad the seller just priced (a live
  listing disappears) or leaves the clock stale. Neither failure is visible in the suite
  unless a test asserts the *new* behaviour.

#### 3.2.1 Decision gate — Q3 (self-edge vs. explicit timer-bump service)

| Option | Change | Pro | Con |
|---|---|---|---|
| **A** | Add a `PUBLISHED → PUBLISHED` self-edge to the hoisted `ALLOWED_TRANSITIONS` and route the price/photo branch through `ad.transition_to(AdStatus.PUBLISHED)`. | Smallest diff; reuses the existing `published_at` reset, the `original_published_at`-once logic and the `published_by` handling; the matrix becomes the single place that says "entering PUBLISHED resets the clock", so a future caller cannot get it wrong. | `transition_to` is also the `refresh_from_db()` + `update_fields` path, so a self-edge must be a **no-op for `status`** — writing `status` into `update_fields` when it is unchanged is harmless today but asserts a transition that did not happen. Any future consumer that treats "a transition occurred" as a signal (an analytics event, a cache bump, a `ModeratorActionLog` row) would double-count. The price fields must be saved in the **same** call, or in a second save, and the ordering matters for the check constraints. |
| **B** | Add an explicit `Ad.reset_publish_timer()` (or an equivalent service method) that touches `published_at` without a status transition, and call it from the price branch. | More honest about intent — it is a clock reset, not a transition; a self-edge in a *state machine* is semantically odd and may confuse a later reader. | **Adds a second writer of `published_at`**, which is precisely the "three partial notions of last seller activity" `VAL-005` warns against. It also duplicates the `original_published_at`-once guard, because the existing logic lives inside the `PUBLISHED` branch of `transition_to` — so the new method must re-derive it or delegate to it. |

**The code context's recommendation is A** ("prefer the self-edge, and land it with `AD-013`
+ `AD-011` in one commit"). **This plan does not record that as a decision.** It is a
recommendation, the trade-off is live, and the `VAL-005` argument against B is not
obviously decisive once the anchor decision (Q4) has been made — the Researcher must
re-derive it against whatever Q4 concludes, because under an anchor that *is* `published_at`,
`VAL-005`'s "three partial notions" objection weakens considerably.

**Researcher must additionally state**, whichever option wins: what `transition_to`
**returns** today (it returns `None` — `Q8` depends on this), whether the price fields are
saved before or after the clock bump, and whether the self-edge is exposed to the admin
form (it will be, once BLOCK 6 routes the form through a sanctioned path — so BLOCK 6 must
know).

**Findings and notes carried forward.**

1. **The defect is a documented spec deviation, not a wording ambiguity.** `db-schema.md`
   says `published_at` is *"UPDATED on every PUBLISHED transition (timer reset)"* and
   decision J extends it to *"price/photo edits"*. The model field's own `help_text` says
   *"Drives archive/delete timers; UPDATED on every PUBLISHED transition"*. Three documents
   already promise the behaviour.
2. **A shipped green test asserts the defect and must change (project rule 2).**
   `apps/ads/tests/test_edit.py::TestPublishedTextEdit::test_edit_published_price_only_stays_published`
   — docstring *"PUBLISHED ad with price-only change -> stays PUBLISHED, **published_at
   unchanged**"* and the assertion `ad.published_at == original_published_at`. It must be
   rewritten in **this** commit, with the reason recorded: the test encoded the defect, and
   production code is king.
3. **The sibling tests in the same class must stay green and must not be touched.**
   `test_edit_published_text_edit_transitions_to_on_moderation` asserts `published_at` is
   **preserved** through the *text* path — an `ON_MODERATION` transition must not reset the
   clock, and a self-edge must not disturb it.
   `test_edit_published_mixed_edit_transitions_to_on_moderation`,
   `test_edit_published_text_edit_passes_auto_moderation` and
   `test_edit_published_text_edit_fails_auto_moderation` are the same family. Touching any
   of them is a scope breach.
4. **The retention anchor is Q4 and this block must not assume it.** `archive_sweep` measures
   60 days from `published_at`; `db-retention.md` documents the same; US-S7 and US-A5 say 2
   months from `published_at` (which the 60-day constant matches) and 4 months for deletion
   (which `delete_sweep` does **not** currently match — that is BLOCK 7). **Resetting the
   clock on a price edit is correct under every candidate anchor**, so this block is not
   blocked on Q4. **Changing the window is BLOCK 7's job** and must not appear here.
5. **A self-edge interacts with `AD-011`.** Under Option A the transition runs the
   `PUBLISHED` branch, which — after BLOCK 1 — also clears `archived_at`. On a
   price-only edit of a `PUBLISHED` ad, `archived_at` is already `None` (BLOCK 1 guarantees
   it), so this is a harmless no-op. State that in the commit message; do not add a guard.
6. **Order of saves matters.** If Option B is chosen, the price fields and `published_at`
   must be written in **one** `save(update_fields=[...])` or in an order that cannot leave
   the row momentarily inconsistent. If Option A is chosen, the price `save()` and the
   transition `save()` are two calls inside one `atomic()` — the view already owns one.
7. **The query-budget guard applies.** `apps/ads/tests/test_ad_detail_queries.py` renders an
   ad-detail page inside `CaptureQueriesContext` with `_QUERY_BOUND = 16` and enumerates the
   budget line by line. This block adds no query to that path, but the test must be run to
   confirm it.

**File surface (semantic units).**
- `src/backend/apps/ads/models.py` → the module-level `ALLOWED_TRANSITIONS` (created by
  BLOCK 1) and, under Option B, a new `Ad`-level timer method.
- `src/backend/apps/ads/views/edit.py` → `ad_edit` (the `status == AdStatus.PUBLISHED`
  branch that is not `has_text_change`) and `_apply_price_change` (read; likely unchanged).
- `src/backend/apps/ads/tests/test_edit.py` → `TestPublishedTextEdit`
  (rewrite `test_edit_published_price_only_stays_published`; add the new case).
- `src/backend/apps/ads/tests/test_ad_lifecycle.py` → `TestTransitionMatrixEdges` (extend
  with the new edge, if Option A).
- Docs: `docs/02-database/db-schema.md` (the `published_at` note — it must state the reset
  now actually happens), `docs/04-user-stories/seller-stories.md` (US-S7 — **only** if Q4's
  answer changes the wording; otherwise no edit).

**Tests required.**
- *Must be **rewritten**:* `test_edit_published_price_only_stays_published` — the docstring
  and the `published_at` assertion both change. Name the reason in a comment: the test
  encoded the defect.
- *Must be added:*
  - A price-only edit of a `PUBLISHED` ad leaves the status `PUBLISHED` **and** moves
    `published_at` **forward** (assert strictly greater than, with a reloaded instance).
  - A photo-only edit behaves identically.
  - The sibling text-path test still proves `published_at` is **preserved** when the ad goes
    to `ON_MODERATION`.
  - Under Option A, a matrix test for the new self-edge and for the fact that the self-edge
    does **not** write a `ModeratorActionLog` row (no moderator is involved).
  - Under Option A, a test that `original_published_at` is **not** overwritten by a
    re-published ad — the existing `TestOriginalPublishedAtImmutability` cases cover this
    and must pass unchanged, but the new self-edge path must be shown to reach them.
- *Must keep passing unchanged:* the rest of `TestPublishedTextEdit`;
  `test_ad_lifecycle.py` in full; `test_ad_detail_queries.py`;
  `apps/core/tests/test_sweep_delete.py` and `test_sweep_lock_structure.py` (no sweep
  change here).
- *Gate:* `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/ src/backend/apps/core/tests/" test`,
  then `.\Makefile.ps1 test`, then both static gates.

**Risk / rollback.**
- *Risk (highest in this block):* Option A's self-edge is later read by a consumer as "a
  transition happened" and double-counts. *Mitigation:* the commit message names the
  constraint; the `update_fields` list is specified explicitly; the "no audit row" test.
- *Risk:* a live listing is auto-archived hours after being priced, because the clock moved
  and `archive_sweep` is hourly. *Mitigation:* this is the intended behaviour under every
  candidate anchor — but the block must say so in the commit message so an operator
  reporting "my ad disappeared" understands it is by design.
- *Risk:* the test rewrite is "fixed" by changing production code back. *Mitigation:*
  §1 restates project rule 2; the block names the test and the reason.
- *Rollback:* the code half and the test half revert together. Reverting the code and
  keeping the test leaves a red suite; reverting the test and keeping the code hides the
  defect. **Revert both or neither.**

---

### BLOCK 3 — Restore the human approval path (VAL-003)

| | |
|---|---|
| **Findings owned** | `05-VAL-003` |
| **`depends_on`** | — (**must land before BLOCK 6**) |
| **Priority** | **P0 — the single most important block in this plan** |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Why this block is first.** `AD-001`'s obvious fix is to make `AdAdmin.status` read-only.
That fix is **catastrophic if it lands alone**, because the four `action_*` buttons and the
review view — the only sanctioned moderator write paths — currently **cannot approve
anything**. `bulk_approve` filters a status the system never commits, the approve view
`get_object_or_404`s on it, and `approve_ad` returns `False` for every real ad. Ship
`status` → read-only first and **moderators lose the ability to publish at all**. This block
is the precondition. §4.2 records the edge.

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- **Implementor — yes.** Always.
- **Auditor — yes.** Must re-derive, at the anchor, every gate that filters on a single
  ad status, and confirm the widen-narrow symmetry with `bulk_reject` and the review **detail**
  view (which already uses the pair). A missed gate means the path is *still* dead after the
  fix, and the block would ship "restored" on an unverified claim.
- **Researcher — yes.** The durable-state semantics of a moderation queue (does a
  human-approvable status have to be the same status a pending ad sits in? how should the
  priority service treat it?) have more than one defensible shape, and the answer
  determines whether BLOCK 5's work is a small widening or a redesign.
- **Planner — yes.** This is a cross-app change (`apps/ads/admin.py`, `apps/moderation/`
  services, `apps/moderation/views/review.py`, `apps/analytics/`) that must preserve the
  response shapes, the `ModeratorActionLog` writes, and four shipped tests. It needs a
  written per-gate design before code.
- **Validator — yes.** **Highest risk in the phase.** The failure mode is *silent*: if a
  gate is missed, the moderation queue still returns 0 and the approve view still 404s, and
  nothing in the suite notices unless the block adds the right tests. A wrong widening is
  worse — it would let a moderator approve an ad in a state that was never designed to be
  approvable.

**Scope: the failure is provably decidable independently of Q2.** This is the key insight
that lets BLOCK 3 land before the `ON_MODERATION` durability decision. Look at the three
gates and at their **already-correct siblings** in the same files:

| Gate | File → symbol | Current | Its sibling in the same file | Sibling's state |
|---|---|---|---|---|
| `bulk_approve` | `apps/moderation/admin_actions.py` → `bulk_approve` | filters **one** status | `bulk_reject` | **already** filters `status__in=[ON_MODERATION, ON_MODERATION_FAILED]` |
| `approve_ad` (service) | `apps/moderation/admin_actions.py` → `approve_ad` | returns `False` unless the ad is in **one** status | — | — |
| Approve view | `apps/moderation/views/review.py` → `approve_ad` (view) | `get_object_or_404(..., status=ON_MODERATION)` | `moderation_review` (detail view) | **already** uses `status__in=[ON_MODERATION, ON_MODERATION_FAILED]` |
| Approve redirect | `apps/moderation/views/review.py` | redirects to `?status__exact=on_moderation` | the reject view's redirect | **same shape** — fine either way |

**`bulk_reject` and the review detail view already treat
`{ON_MODERATION, ON_MODERATION_FAILED}` as the approvable set.** So the approvable set is
**already defined in this codebase, twice, by the two paths that work**. The defect is that
the approve path was written against a narrower set than its own siblings use.

**This makes the minimal correct fix independent of Q2**: widen the three approve gates to
the pair the siblings already use. Under Q2 (i) — `ON_MODERATION` becomes durable — the
widen is still correct and still necessary (the status set is unchanged, only its occupancy
grows). Under Q2 (ii) — same transaction — the widen is the *entire* fix for the human
path. Under Q2 (iii) — `ON_MODERATION` dropped from the durable set — the widen is *also*
the correct and only fix, because `ON_MODERATION_FAILED` is the only status that survives.

**`bulk_reject` and `bulk_approve` are also the buttons that DO work** (`action_reject`,
`action_soft_delete`, `action_ban_user` all write their `ModeratorActionLog` rows today).
The fix makes the approve button join them; it does not remove any surface. **This block
must not delete the `action_approve` button** — that is Q1's territory (BLOCK 6).

**Findings and notes carried forward.**

1. **Do not route manual approval through `auto_moderate`.** The report's own AD-001
   "refuted sub-claims" forbid it: it would re-apply the *automatic* criteria (banned
   words, duplicate-title) over a decision a human moderator has already made, and would
   **fail** an approve the moderator deliberately overrode. It also contradicts US-A3's
   *"Actions are instant"*. Phase 15's validator independently states *"reject and ban are
   the only working moderator write actions"* — the fix is to make **approve** work like
   them, not to build a new pipeline.
2. **`ON_MODERATION_FAILED → PUBLISHED` is refused by the matrix, and that is correct.**
   The `ALLOWED_TRANSITIONS[ON_MODERATION_FAILED]` set is `{REJECTED}`. A widened gate would
   then hand `approve_ad` an ad whose transition raises `ValueError`. **The state machine
   is not the thing to change here** — the matrix question belongs to BLOCK 5 (Q2 option i
   makes `ON_MODERATION` durable and therefore the *right* source of approvable ads) and to
   BLOCK 2's edge set. **BLOCK 3 must decide, in writing, what the widened gate does when
   the target transition is refused** — and the honest answer is that it should surface the
   state machine's own error to the moderator rather than swallow it, exactly as BLOCK 9
   does for the bulk API. This is the block's hardest design question and it is why the
   block carries a Researcher and a Planner.
3. **The `ModeratorActionLog` write must not be lost.** `bulk_approve` currently calls
   `moderation_log.set_published(...)` (or the equivalent) for each ad; widening the filter
   changes **which** ads reach that call, never **how** it runs. Every existing assertion
   about the audit row must stay green.
4. **Four shipped tests currently assert the *dead* behaviour and will change meaning.**
   `apps/moderation/tests/test_moderation_views.py::TestApproveAdView` —
   `test_approve_transitions_to_published` and `test_approve_creates_moderation_log`
   (both fabricate `ON_MODERATION`, so they stay green after the widen and **prove nothing** —
   they must be retargeted onto a reachable state per BLOCK 4's taxonomy), and
   `test_approve_non_moderation_ad_returns_404` (**this one pins the 404 and must be
   rewritten** — it is the finding, written as a test). Plus
   `apps/moderation/tests/test_admin_actions.py::TestBulkOperations::test_bulk_approve_publishes_all`
   (asserts `== 3` against fabricated rows).
5. **The source-inspection guard is a constraint on the fix's shape.**
   `TestBulkLockingStructure::test_bulk_approve_uses_select_for_update_orderby_atomic`
   asserts `"select_for_update"`, `"order_by"` and `"pk"` appear in
   `inspect.getsource(bulk_approve)`. **Any rewording that drops one of them turns the
   guard red** — and the guard is asserting a real invariant, so the fix must preserve all
   three, not delete the test.
6. **Phase 04's tripwire applies.** `apps/users/tests/` carries
   `test_bulk_ban_users_not_locked`, asserting `select_for_update` is **not** issued on the
   bulk-**ban** path. This block must not add locking to `bulk_ban_users`.
7. **Do not add an alert.** Phase 12 checked: no Prometheus is deployed and no rule
   references moderation-queue depth, so a `pending_moderation` alert is dead on arrival
   today. If phase 12's `OPS-003` lands first, **this block must carry its warning forward**
   — a new alert on a queue that this block restores would fire on real numbers for the
   first time and must be validated against them (§5.2).
8. **`get_pending_queue_size()` is unaffected by the widen** — it counts
  `status=ON_MODERATION` specifically, and the analytics dashboard is a *pending auto-check*
  metric, not an *approvable* metric. **Do not change it here.** Q2 decides what it means.

**File surface (semantic units).**
- `src/backend/apps/moderation/admin_actions.py` → `bulk_approve` (its status filter) and
  `approve_ad` (its status guard). `bulk_reject`, `bulk_ban_users`, `bulk_delete`,
  `soft_delete_ad` are **read-only** for this block.
- `src/backend/apps/moderation/views/review.py` → the `approve_ad` view's
  `get_object_or_404` gate. `moderation_review` (the detail view) is **already correct and
  must not change**.
- `src/backend/apps/moderation/services/priority.py` → `PriorityService.get_queued_ads` and
  `get_priority_counts` **read only**, unless the Researcher's design changes their contract
  (recorded in the commit message if it does).
- `src/backend/apps/ads/admin.py` → `AdAdmin.action_approve` — **read only.** The button
  stays; the filter below it is what changes.
- `src/backend/apps/moderation/tests/test_moderation_views.py` →
  `class TestApproveAdView` (rewrite `test_approve_non_moderation_ad_returns_404`; retarget
  the other two).
- `src/backend/apps/moderation/tests/test_admin_actions.py` → `class TestBulkOperations`
  (retarget `test_bulk_approve_publishes_all`) and `class TestBulkLockingStructure`
  (**keep unchanged** — it is the guard).
- **Not touched:** `src/backend/apps/analytics/services/moderation_analytics.py`
  (`get_pending_queue_size`), `apps/ads/admin.py`'s `readonly_fields`.

**Tests required.**
- *Must be **rewritten**:* `TestApproveAdView::test_approve_non_moderation_ad_returns_404`.
  The new test must assert what actually happens for a genuinely un-approvable status
  (e.g. `PUBLISHED`, `DELETED`, `DRAFT`) and must be demonstrated **red** against the
  pre-fix code for the `ON_MODERATION_FAILED` case.
- *Must be **retargeted** (not deleted):* `TestApproveAdView::test_approve_transitions_to_published`
  and `::test_approve_creates_moderation_log`; `TestBulkOperations::test_bulk_approve_publishes_all`.
  Each must reach its state **through a status the system can actually produce**. Where the
  correct state is `ON_MODERATION_FAILED`, that is a status production reaches today
  (a real `submit_ad` that fails a criterion), so these tests are retargeted in BLOCK 4's
  taxonomy — **do not leave them fabricating `ON_MODERATION`**, because after this block
  they would pass against a state the system still cannot produce.
- *Must be added:*
  - An end-to-end assertion that `bulk_approve` on a queryset containing a
    genuinely-approvable ad returns a **non-zero** count, with a `ModeratorActionLog` row
    and a `published_at` written. This is the finding's direct regression guard.
  - The approve view returns **2xx** (not 404) for an approvable ad and performs the
    transition and the audit write.
  - A test that a status outside the approvable pair is **rejected with an actionable
    message** and a `ModeratorActionLog` row is **not** written.
  - A test for the refused-transition case named in note 2: the state machine's `ValueError`
    must reach the moderator as a message, not as a silent no-op and not as a 500.
- *Must keep passing unchanged:*
  `TestBulkLockingStructure::test_bulk_approve_uses_select_for_update_orderby_atomic`;
  `TestBulkOperations`'s `bulk_reject` cases; `test_bulk_ban_users_not_locked` (phase 04);
  `apps/moderation/tests/test_moderation_log.py`; every existing `ModeratorActionLog`
  assertion.
- *Gate:*
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/moderation/tests/ src/backend/apps/ads/tests/" test`,
  then `.\Makefile.ps1 test`, then both static gates.

**Risk / rollback.**
- *Risk (the one that matters):* the block ships claiming the path is restored and a gate was
  missed, so it is still dead — and BLOCK 6 then removes the raw form path. *Mitigation:*
  the end-to-end non-zero-count test and the 2xx test are **mandatory** and must be
  demonstrated red before the fix.
- *Risk:* the widen is over-read as "a moderator may now approve anything". *Mitigation:*
  the pair is not "anything" — it is the pair the codebase already defines; and the
  refused-transition test proves the state machine still guards the edge.
- *Risk:* a gate is widened and the `ModeratorActionLog` write is bypassed for a newly
  reachable status. *Mitigation:* the audit-row assertions are kept green and a new one is
  added for the newly reachable status.
- *Rollback:* one commit, no migration, no schema. Revert restores the dead path — which is
  exactly the state BLOCK 6 must not ship into, so **if this block is rolled back, BLOCK 6
  must be rolled back with it.**

---

### BLOCK 4 — Make the test suite reach `ON_MODERATION` the way production does (VAL-002)

| | |
|---|---|
| **Findings owned** | `05-VAL-002` (and the **retargeting** of the tests BLOCK 3 touches) |
| **`depends_on`** | BLOCK 3 (soft — it shares test files with BLOCK 3's retargeting); **hard-precedes BLOCK 5** |
| **Priority** | **P0 — the rollout-safety precondition for BLOCK 5** |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Why this block exists separately.** `VAL-002` is not a defect in production code; it is a
defect in the **oracle**. If BLOCK 5 (make `ON_MODERATION` durable) lands first, roughly
half the fabricated tests stay green — they now pass against a state that has become real —
so the suite would report success while having validated **nothing** about the new durability
path. The migration must land first, in its own commits, so that BLOCK 5 has a suite that
can actually fail.

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- **Implementor — yes.** Always.
- **Auditor — yes.** Must produce the **census** (§3.4.1). The report's `34` is a floor and
  the code context's re-measurement is also a floor; both were taken before concurrent
  commits landed. The real number determines the block's size and the replacement default.
- **Researcher — yes.** The taxonomy (which fabricated call sites are *legitimate* — a test
  of the moderation queue legitimately needs a pending ad — versus *illegitimate* — a test
  of the auto-moderation pipeline that fabricates the state instead of driving it) is a real
  judgement with a large blast radius, and the replacement default (Q10) trades unrelated
  breakage against clarity.
- **Planner — yes.** This is the largest mechanical change in the plan: two shared conftests,
  an unknown number of call sites across a dozen-plus files, and a mandatory internal order.
  It needs a written triage rule before code, and the rule must be applied consistently.
- **Validator — yes.** The failure mode is a suite that is green for the wrong reason, which
  is precisely the failure this block exists to eliminate. Independent review must confirm
  the census was complete and no fabrication channel survives.

#### 3.4.1 Mandatory pre-step — the census (Auditor, before any code)

The Auditor must run, at the anchor, and record in the block's task `extra_context`:

1. **The fixture-default channel.** Confirm the `status` parameter default in
   `create_test_ad` **and** `create_test_ads_bulk` in **both** `src/backend/conftest.py`
   and `src/telegram_bot/tests/conftest.py`, and count every call site that **omits**
   `status=`. The code context measured ~62 backend-side at its anchor; **the number must be
   re-measured, not inherited.**
2. **The explicit channel.** Count every `status=AdStatus.ON_MODERATION` occurrence and
   separate **production** from **test** from **cleanup** (`.delete()` in a test is not a
   fabrication). The report's own grep of `34` includes at least one production hit
   (`bulk_approve`) and one cleanup call.
3. **The triage rule.** Classify each test-side site as:
   - **(a) Consumer test** — tests a surface that *reads* `ON_MODERATION` (the queue view,
     the priority service, `bulk_approve`, `get_pending_queue_size`, the dashboard bucket).
     These may legitimately need a pending row, and after BLOCK 5 the state is real, so a
     **directly created** row is honest. **These need no rewrite** once BLOCK 5 lands.
   - **(b) Producer test** — tests a surface that *writes* `ON_MODERATION`
     (`submit_ad`, `ad_reactivate`, `auto_moderate`). These currently fabricate the state
     instead of driving it. **These must be retargeted** onto a reachable state, and they
     are the ones that make the suite a real oracle.
   - **(c) Incidental** — a row created for an unrelated assertion. These should get an
     explicit `status=` so they stop depending on the default at all.
4. **The per-file result** must be recorded so BLOCK 5 can assert on it afterwards.

#### 3.4.2 Decision gate — Q10 (the replacement default status)

The **mechanism** is decided: change the default first, in its own commit, so the silent
channel becomes loud failures and the failure list *is* the migration map. The **value** is
not, because it trades unrelated breakage against clarity.

| Candidate | What it converts silently into a failure | Con |
|---|---|---|
| `PUBLISHED` | ~62 rows that are currently `ON_MODERATION` and are almost certainly **not** asserting anything about moderation — most are in `test_price_normalizer.py`, `test_priority*.py`, `test_auto_moderation.py`. `_set_status_timestamp` already sets `published_at` for it, so the constraints are satisfied. | The largest failure list. But the code context's reading is that most of these tests are about **published listings** and are green *by accident* of a default nobody chose deliberately. **Recommended, but not decided here.** |
| A required keyword (`status: AdStatus` with **no** default) | Every omission becomes a `TypeError` at collection time. | Maximum clarity, and it makes the *entire* remaining census loud. But it is a large, noisy diff across every test file in the repository, including files no phase-05 finding touches — which is exactly the scope-creep shape project rule 7 warns against. |
| `DRAFT` | Same count, and `DRAFT` is `uq_ads_single_draft_per_user`-constrained, so `create_test_ads_bulk` could start colliding. | Introduces a per-seller uniqueness constraint into a bulk fixture. **Actively worse** — reject unless the Auditor finds a reason. |

**The Planner must record the chosen value, the count it converts into failures, and the
triage disposition of each resulting failure**, in the block's task `extra_context` and in
the commit message. **The failure list is the deliverable** — it is the migration map for
BLOCK 5 and the audit trail for the final report.

**Findings and notes carried forward.**

1. **Both conftests must change together.** `src/telegram_bot/tests/conftest.py` **redefines**
   `create_test_ad` and `create_test_ads_bulk` for the bot package — bot tests **cannot**
   import the backend conftest. A one-sided change leaves the bot suite fabricating a state
   the bot package can never reach either. This is a **hard** requirement, not a nicety.
2. **`_set_status_timestamp` is the reason the default has never broken a constraint.**
   `create_test_ad` calls it so every status-specific `CheckConstraint` is satisfied for
   whatever status is passed. Changing the default therefore does **not** red the DB
   constraints — it reds the **assertions** that depended on `ON_MODERATION` semantics. That
   is the desired signal, but the implementor must understand *why* there is no `IntegrityError`
   in the failure output, or they will chase a phantom.
3. **`create_test_ad` is the most contended file in the repository** (§5.3). Phase 03's plan
   states outright that phase 03 **must not edit it at all**. This block is the **one**
   justified exception in the plan, because it is the finding. It must:
   - change **only** the `status` default (and any docstring describing it);
   - touch **no other** fixture, **no** other parameter, **no** formatting;
   - be re-read immediately before editing;
   - be staged by explicit path.
4. **The retargeting rule for category (b) producer tests.** A producer test must not
   fabricate `ON_MODERATION`; it must either (i) drive the real path — call `submit_ad` or
   `ad_reactivate` and assert the **observable outcome** (published or failed), or (ii) if the
   test is specifically about the *transition into* `ON_MODERATION`, it must be rewritten to
   assert the durable post-BLOCK-5 state once that state exists. **Category (b) tests are the
   only ones that must change; over-rewriting (a) tests is scope creep.**
5. **This block must not change production code.** If a failure reveals a production defect
   that is **not** `ON_MODERATION`-related, record it and route it — do not fix it here.
6. **A failing suite is an expected intermediate state.** The default-change commit is
   **deliberately red** by construction. The block therefore has a **mandatory internal
   order** and the red commit is never pushed alone: the internal order below ends with a
   green suite, and §8.2 requires the whole sequence to be green before the block is closed.
7. **Do not run the nightly `seed` suite.** Nothing here touches seeding. `PYTEST_SKIP_MARKERS=seed`
   is the correct gate throughout.

**Mandatory internal order.**
`(a)` census (Auditor) → `(b)` change both fixture defaults, commit — *red by
construction* → `(c)` read the failure list, apply the triage rule per file, commit →
`(d)` retarget category (b) producer tests, commit → `(e)` re-run the full fast gate, green →
`(f)` record the census and the triage in the plan/commit message.

**File surface (semantic units).**
- `src/backend/conftest.py` → `create_test_ad`, `create_test_ads_bulk`, `_set_status_timestamp`
  (**read only** — the last one must not change).
- `src/telegram_bot/tests/conftest.py` → the redefined `create_test_ad` /
  `create_test_ads_bulk`.
- Every test file the census implicates — the exact list is the census output and is **not**
  enumerated here, because the tree drifts. The block's `extra_context` carries it.
- **Not touched:** any production module.

**Tests required.**
- This block's deliverable **is** the test suite's own fidelity. It adds no new test for its
  own sake; the acceptance criteria are:
  - *Must be added:* a regression guard that **no** test fabricates `ON_MODERATION` through
    the fixture **without an explicit, justified `status=`**, so a future default change
    cannot silently re-open the channel. It must be **red** against the pre-fix conftests.
  - *Must be added:* the census itself as a **committed, readable artifact inside a test
    module docstring or a plan file update** — a comment in `conftest.py` naming the
    convention, so the next person does not re-introduce a default of `ON_MODERATION`.
  - *Must be retargeted:* every category (b) producer test.
  - *Must keep passing unchanged:* every category (a) consumer test, **without edits** —
    if a consumer test needs editing to survive the default change, it was mis-classified
    and the classification must be revisited before the edit.
- *Gate:*
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed test` (full fast suite — the census is a
  whole-suite property, not a file property), then both static gates.

**Risk / rollback.**
- *Risk:* the default change is committed alone and leaves the repository red. *Mitigation:*
  the mandatory internal order; §8.2 requires green before the block closes; the block is
  never closed mid-sequence.
- *Risk:* over-rewriting — a mechanical sweep "fixes" category (a) consumer tests that were
  fine, inflating the diff across a dozen files and touching code no finding implicates.
  *Mitigation:* the triage rule is explicit; the Auditor classifies, the Implementor applies.
- *Risk:* `conftest.py` is edited on a stale read and another phase's edit is clobbered.
  *Mitigation:* §1 staging rule; re-read immediately before editing; explicit paths.
- *Risk (the one that would silently defeat the plan):* the census is **narrower** than
  reality — the report's `34` and the code context's `93` are both floors taken at
  different anchors, and concurrent commits have landed since. *Mitigation:* the Auditor
  re-measures; the block records the number it actually found; §8.3 checks that BLOCK 5's
  green state came **after** a red baseline.
- *Rollback:* revert the commits in reverse order. Rolling back the default change but
  keeping the retargeted tests is harmless; rolling back the retargeting and keeping the
  default change re-opens the silent channel.

---

### BLOCK 5 — Make `ON_MODERATION` a durable state (AD-008, Q2)

| | |
|---|---|
| **Findings owned** | `05-AD-008` |
| **`depends_on`** | **BLOCK 4 (hard)** · BLOCK 3 (hard — the approval path must exist for the state to be worth having) |
| **Priority** | P0 |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**This block is owner-gated. It must not write code before Q2 is answered.** See the gate
below and §0.5.

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- **Implementor — yes.** Always.
- **Auditor — yes.** Must re-derive, at the anchor, **both** production writers of
  `ON_MODERATION` and prove there is no third, and must confirm no other query filters the
  state in a way the change would alter.
- **Researcher — yes.** This is the one block in the plan that changes a **transaction
  boundary around a business-critical write**. The durability options have real
  distributed-systems consequences (a committed-but-never-moderated ad, a lost moderation
  verdict on crash) and more than one defensible design exists.
- **Planner — yes.** Transaction-boundary redesign, cross-app consumer review, a large
  test-migration contract, and a decision that changes what four documents promise.
- **Validator — yes.** **The highest-consequence block after BLOCK 6.** The failure mode
  is subtle: an ad can become durably `ON_MODERATION` and then **never leave** that state —
  invisible to a seller, invisible to the queue if it is not filtered, and reaped by
  nothing. Nothing in the existing suite can see that.

#### 3.5.1 Owner gate — Q2 (which side of `ON_MODERATION` durability?)

**This is a product decision, not an implementor's and not a Planner's.** It is routed to
the coordinator. The options and their consequences are recorded here so the owner can
decide with the costs in front of them.

| Option | Change | Pro | Con |
|---|---|---|---|
| **(i)** | Commit `ON_MODERATION` and run `auto_moderate` **outside** the write transaction — either in a second transaction, or asynchronously (a worker/management command). | The state becomes observable; the queue, the priority service, `get_pending_queue_size` and the dashboard bucket all become real; the human approval path (BLOCK 3) becomes genuinely populated; four documents become true. | Introduces a **window** in which an ad is durably pending and nothing is moderating it. That window must be bounded and recoverable: an ad left in `ON_MODERATION` by a crashed worker is a live defect. The recovery mechanism (a sweep, a re-drive, a timeout) is **part of the option, not an afterthought** — and it is a new scheduler surface. `max_ads_per_user` enforcement moves: `set_published` is currently called inside the same transaction as the `ON_MODERATION` write, so a user at their cap must not be able to accumulate a queue of pending ads that all publish at once when the cap is lifted. |
| **(ii)** | Commit `ON_MODERATION` and run `auto_moderate` in the **same** transaction anyway. | Smallest diff. | **Fixes nothing.** The state is still never observed, because the transaction still never ends with the ad in `ON_MODERATION`. The report and the code context both state this plainly. It is listed only so the owner can rule it out explicitly. |
| **(iii)** | Remove `ON_MODERATION` from the durable set; delete the queue UI, the priority queue, `get_pending_queue_size`, and the US-A12 / US-A13 / `db-enums.md` / decision-Q commitments. | Honest. The state does not exist, so stop pretending. The code is already (i)-shaped. | **A scope explosion, not a patch.** It deletes a moderation queue four documents promise the business bought, and it changes US-A12's "priority queue" and US-A13's "pending queue size" — user-story deletions, not engineering work. The report explicitly warns this branch "deletes the queue the business asked for". **This plan does not pick it**, and if it is chosen the block grows by the whole deletion surface. |

**Researcher must additionally state**, for whichever option wins: what happens to an ad
left in `ON_MODERATION` when the moderating process dies; whether the moderation verdict is
at-least-once or at-most-once; and how `ModeratorActionLog` rows stay single-valued.

**Findings and notes carried forward.**

1. **There are exactly two production writers, and both are named in the code context.**
   `submit_ad` (`src/backend/apps/ads/services/submission.py`) and `ad_reactivate`
   (`src/backend/apps/ads/views/edit.py`). Both call `transition_to(ON_MODERATION)` and then
   `auto_moderate()` **in the same `atomic()`**. `submit_ad`'s own comment already states the
   consequence verbatim: *"If `auto_moderate` raises, the entire `submit_ad` transaction
   rolls back — the ad stays DRAFT (not committed in ON_MODERATION)."* **That comment is
   wrong under option (i) and is a named deliverable of this block.**
2. **Four documents promise the state.** US-S2 (*"On submit → `ON_MODERATION`, not visible
   until checks pass"*), US-A12 (priority queue), US-A13 (pending queue size),
   `docs/02-database/db-enums.md` (*"awaiting auto-check (hidden)"*) and decision Q. Under
   option (i) they become true and need no edit beyond the corrected comment. Under option
   (iii) they must all be edited — which is why (iii) is a scope explosion.
3. **`auto_moderate`'s internal `atomic()` blocks are currently savepoints**, nested inside
   `submit_ad`'s outer block. **Option (i) changes that nesting depth** and therefore
   interacts with phase 03's `03-DB-002` reasoning about `record_event` and the caller's
   transaction boundary. **Phase 03 BLOCK 3 must be re-read if it has already landed** (§5.2).
4. **The `_pass_moderation` bare `except Exception` is Q7** and is *not* fixed here, but
   option (i) makes it **worse**: today a failure inside `_pass_moderation` is caught and the
   ad is failed *within the same transaction*, so the seller's content verdict is at least
   consistent with the ad's state. Under option (i) the same bare handler would mark an ad
   failed for a **system** error, in a second transaction, with no compensation. **Q7 must
   be answered before option (i) ships.** This is the one place where BLOCK 5 and BLOCK 12
   genuinely interact, and it is why BLOCK 12's Q7 is not a free choice.
5. **The consumers all need review, not change.** `get_pending_queue_size` (analytics),
   `PriorityService.get_queued_ads` / `get_priority_counts`, the moderation queue view, the
   review views, `AdAdmin.changelist_view`'s `moderation_queues` preset, and the seller
   dashboard's "On Moderation" bucket. Under option (i) most of these need **no** change —
   they were written for a state that did not exist. The block must confirm each one rather
   than assume it.
6. **The seller dashboard bucket is the seller-visible half.** Under option (i) a seller can
   see "On Moderation" for the first time. `src/backend/templates/ads/dashboard.html` already
   has the bucket; if the bucket's empty-state copy or its Edit affordance assumes the
   status is transient, that is now user-visible. **The Researcher must check the template**,
   and any new string is an i18n obligation.
7. **`max_ads_per_user` is the business invariant most at risk.** `set_published` is the
   authoritative guard and it takes a `User.objects.select_for_update()` row lock. Under
   option (i), N ads of one seller can be pending simultaneously and the guard is evaluated
   N times in N separate transactions. The Researcher's design must state whether the cap is
   checked at submit time (as now) or at publish time (as the guard is written), and what
   happens to the surplus.
8. **Visibility.** A durably-`ON_MODERATION` ad must stay out of the public queryset.
   `ListingsQuery.build_queryset` filters `status=AdStatus.PUBLISHED`, so this holds by
   construction — **verify it, do not assume it**, because the block is making the state real
   for the first time.

**File surface (semantic units).**
- `src/backend/apps/ads/services/submission.py` → `submit_ad` (the `ON_MODERATION`
  transition, the `auto_moderate` call, and the comment that says the state is never
  committed) and `SubmitAdInput` (read).
- `src/backend/apps/ads/views/edit.py` → `ad_reactivate` (the same pair).
- `src/backend/apps/moderation/services/auto_moderation.py` → `auto_moderate`,
  `_pass_moderation`, `_fail_moderation` — **read only unless the Researcher's design
  requires a boundary change**, which must then be recorded in the commit message.
- Consumers — **read and confirm, change only if forced**:
  `apps/analytics/services/moderation_analytics.py::get_pending_queue_size`,
  `apps/moderation/services/priority.py::get_queued_ads` / `get_priority_counts`,
  `apps/moderation/views/queue.py`, `apps/ads/admin.py::AdAdmin.changelist_view`.
- `src/backend/templates/ads/dashboard.html` — the "On Moderation" bucket.
- `src/backend/apps/ads/tests/test_submission.py` → the two named cases in note 12 below.
- Docs: `docs/02-database/db-enums.md` (verify, not necessarily edit), and — **only** under
  option (iii) — US-S2 / US-A12 / US-A13 in `docs/04-user-stories/`. **Never**
  `docs/01-spec/technical-specification.md` (phase 06 owns it).

**Tests required.**
- *Must keep passing unchanged and now mean something:*
  `test_submission.py::test_submit_ad_rolls_back_when_auto_moderate_raises` and
  `::test_submit_ad_commit_when_auto_moderate_passes`. Under option (i) the first one's
  **name becomes wrong** — the ad is no longer rolled back to `DRAFT`, it stays
  `ON_MODERATION` and is retried. It must be **rewritten**, not deleted, and the commit
  message must say why.
- *Must be added:*
  - An ad that is durably `ON_MODERATION` between the two transactions, observed from a
    **separate** connection (the only way to prove durability is a test that cannot see the
    uncommitted row).
  - The ad is **absent** from `ListingsQuery.build_queryset` while pending.
  - A crash/exception in the moderating step leaves the ad recoverable — either retried or
    swept, per the option chosen. **Without this test option (i) is not shippable.**
  - `get_pending_queue_size()` returns the real number for the first time.
  - `bulk_approve` and the approve view now have members to act on (the BLOCK 3 tests,
    retargeted onto a genuinely produced state).
  - The `max_ads_per_user` interaction from note 7, per the chosen design.
- *Must keep green:* all of BLOCK 4's retargeted tests; BLOCK 3's end-to-end approval tests
  (they are the direct consumer of the newly real state); `test_ad_lifecycle.py`;
  `test_transition_concurrency.py`.
- *Gate:* `.\Makefile.ps1 test-recreate` is **not** required (no schema change), but
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed test` (full fast suite) is, then both static
  gates.

**Risk / rollback.**
- *Risk (data integrity):* an ad is committed as `ON_MODERATION` and the moderating step
  never runs. It is invisible to the seller, invisible to any consumer that filters the
  status out, and reaped by nothing. *Mitigation:* the recovery mechanism is part of the
  option and the recovery test is mandatory.
- *Risk (business invariant):* `max_ads_per_user` is bypassed by concurrent pending ads.
  *Mitigation:* note 7's test.
- *Risk:* a "green" suite that did not test durability, because BLOCK 4 was skipped or
  de-scoped. *Mitigation:* the hard `4 → 5` edge; §8.3.
- *Risk:* `auto_moderate`'s bare handler turns a system error into a content verdict across
  a transaction boundary (Q7). *Mitigation:* Q7 is answered before (i) ships.
- *Rollback:* **hardest block in the plan to roll back.** Reverting the code while a real
  queue exists re-creates the "ad committed in `ON_MODERATION`, nothing moderates it"
  state. The rollback plan must state what happens to any ad already sitting in
  `ON_MODERATION` at revert time — most likely a one-off query to re-drive or fail them.
  **Write that query into the block before shipping.**

---

### BLOCK 6 — One sanctioned write path for ad lifecycle state in the admin (AD-001, Q1, Q8)

| | |
|---|---|
| **Findings owned** | `05-AD-001` |
| **`depends_on`** | **BLOCK 3 (hard — `VAL-003` must be fixed first)** · BLOCK 1 (hard — the matrix must be a named value) |
| **Priority** | **P0 — the CRITICAL, and the last of the moderation chain** |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**This block is owner-gated (Q1) and must not write code before the owner answers.** The
code context is explicit that *"this is not derivable from the code — no document in
`docs/` says the admin change form is a supported surface."*

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- **Implementor — yes.** Always.
- **Auditor — yes.** Must introspect the **live** `AdAdmin` form at the anchor (not the
  source) and record the exact editable field set, and must re-derive every `Ad` write path
  in the admin tier — including `changelist_view`'s `moderation_queues` preset and the four
  `action_*` buttons — so the sanctioned path is not one of several.
- **Researcher — yes.** Q1 is an architecture question with three defensible answers and
  different blast radii, and Q8 (`transition_to` returns `None`, so the form's save must
  learn the previous status) has more than one honest implementation. The report's own
  §CRITICAL table says *"a patch is insufficient"*.
- **Planner — yes.** New business logic must not land in a `ModelAdmin` method body
  (project rule 3), so this block almost certainly needs a service. That is a design with
  a transaction boundary, a permission check and an audit row, plus a migration-adjacent
  decision about which timestamps the form supplies.
- **Validator — yes.** **The only CRITICAL in the phase.** It changes an **authorization
  surface** and an **audit trail**. A wrong answer either removes a capability operators
  rely on or leaves the unlogged write in place.

#### 3.6.1 Owner gate — Q1 (may a moderator move an ad's status, and through which seam?)

| Option | Change | Pro | Con |
|---|---|---|---|
| **(a) No** | `status` becomes read-only on `AdAdmin` **immediately**; the dead `action_approve` button is removed; US-A3's *"change status"* is withdrawn in `docs/04-user-stories/admin-stories.md`. | The smallest possible fix for the audit hole, and it is already the de-facto security posture for the four *other* writers. | **Removes a capability the owner explicitly authorised** (US-A3: *"change status"*). Requires a user-story edit. BLOCK 3 becomes unnecessary — and is still worth shipping, because the reject/ban/soft-delete buttons are how the remaining moderation works. |
| **(b) Yes, through a service** | `AdAdmin.save_model` is overridden to route a status change through `moderation_log.set_published` / `set_rejected` (which already write the `ModeratorActionLog` row); `status` becomes read-only in the form; the four `action_*` buttons are the sanctioned seam. | Satisfies US-A3's *authorisation* **and** its *logging* requirement with one mechanism; makes the audit row non-optional; the buttons already have tests. | **Requires BLOCK 3 first** — the buttons cannot approve anything until then. Adds an `AdAdmin` override whose body is real business logic, which is why it needs a service underneath. The report's refuted-sub-claims list explicitly **forbids** routing it through `auto_moderate` (it would re-apply automatic criteria over a human decision and contradict *"actions are instant"*). |
| **(c) Yes, through the raw form** | Keep the form as the seam; fix only the four unambiguous violations: the missing audit row, the mutable `original_published_at`, the silent owner transfer, and the two HTTP 500s. | No capability is lost; the audit hole closes. | Requires detecting "was this a status change?" inside a `ModelAdmin` save, which means diffing against a reloaded instance — a fragile pattern. Leaves four other lifecycle fields (`archived_at`, `deleted_at`, `published_at`) form-writable with no invariant, and the DB check constraints are one-directional so the database will not catch a bad combination. |

**The tree supports none of them and is not evidence for any.** US-A3 authorises *"change
status"* **and** requires it to be *"logged to `ModeratorActionLog`"*; US-A10 constrains
only the *automatic* gate; `technical-specification.md` grants the moderator unpublish and
review powers. The report notes the code satisfies the authorisation and violates the
logging half. **The conflict is between two true readings of the same documents, so it is
the owner's to resolve.**

**Regardless of which option wins, four things are unambiguous and MUST be fixed** — the
report's own "unambiguous violations":

| # | Violation | Why it is not a choice |
|---|---|---|
| 1 | **No `ModeratorActionLog` row** | US-A3 requires moderation actions to be logged; the form writes zero. US-A13's moderator-performance metric reads `published_by`/`moderated_by`, so the action is also invisible to reporting. The validator proved the hole **by contrast** (the service path writes 1, the form path 0), not by absence of evidence. |
| 2 | **`original_published_at` is mutable** | `db-schema.md` and the model `help_text` both declare it **IMMUTABLE, audit only**, and decision J says it "does NOT drive sweep". It exists as a first-publication marker. The form lets anyone rewrite it. |
| 3 | **Silent owner transfer** | `user` is editable, so one save moves the ad, its analytics and its `AdFavorite` rows to another account. **No story authorises changing an ad's owner** — US-A3's *"ban all of a user's ads"* presumes the ad set, not a reassignment. Phase 15's validator independently confirmed AD-001 is *"the only writer that can move an ad between owners"*. |
| 4 | **Two hard HTTP 500s** | `readonly_fields` omits `rejected_at` and `moderation_failed_at`, so a form save selecting `REJECTED` or `ON_MODERATION_FAILED` raises an uncaught `IntegrityError` from the `CheckConstraint` instead of a validation message. The constraints **do** fire — they fire too late. |

**Also decided regardless of Q1** (the report's advisory recommendations, cheap and
uncontested): drop the four `search_vector*` fields from the form. The
`ads_search_vector_update` trigger rewrites the column on every insert/update, so a manual
edit is silently discarded — *"a form field that silently discards input is a future trap."*
**Do not** drop the four `action_*` buttons under option (b) — they are the sanctioned
seam.

#### 3.6.2 Decision gate — Q8 (where does the audit row come from, and which action type?)

`ModeratorActionType` has `reject`, `ban_account`, `soft_delete`, `other`.
`moderation_log.set_published` already writes `log_manual_publish` (`action_type=OTHER`,
`reason="Manually published by moderator"`) when a `moderator_id` is supplied. So option
(b) has a ready-made writer — but the sub-problems are real:

- `transition_to` **returns `None`**. The form's save must know the **previous** status to
  know which audit row to write. Two shapes: (i) `save_model` reads `obj.status` before
  `super().save_model(request, obj, form, change)` and compares against a reloaded
  instance; (ii) `transition_to` starts returning the previous status — a **return-value
  change that touches every caller** and is therefore out of scope for this block unless
  the Researcher shows the call-site inventory is small. **The Planner must choose and say
  which, and must name every caller that a signature change would touch.**
- Under option (c) the same problem arises for a plain `obj.save()`.
- The `2 HTTP 500s` fix and the `original_published_at` / owner-transfer fixes are
  **independent of the audit-row question** and can be designed in parallel with it.

**Findings and notes carried forward.**

1. **The terminal-state resurrection is the sharpest evidence.** `Ad.transition_to` refuses
   every transition out of `DELETED` with a `ValueError`, but the form never calls it, so
   `DELETED → published` is a plain `UPDATE` and returns **302**. The terminal-state rule is
   not merely bypassed, it is inverted.
2. **The wrong-timer consequence is the CRITICAL example, not a side effect.** A moderator
   sets `published_at` 999 days in the past; the very next `archive_sweep` run moves the ad
   straight to `ARCHIVED`. A moderator sets it far in the future; the ad is unarchivable
   for years. Both are operator actions with no validation.
3. **There is no `AdAdmin` change-form test anywhere in the tree.** Every test that looks
   like coverage (`TestOriginalPublishedAtImmutability`) exercises `transition_to` **only**
   — the path where the immutability already holds. **The mutability lives in the form,
   where nothing tests it.** Adding a change-form test is therefore a first-class deliverable
   of this block, not an optional extra, and it must be demonstrated **red** first.
4. **`has_change_permission` / `has_view_permission` are overridden to
   `is_staff or is_superuser` with no `obj` check.** The report treats the whole class as
   gated on staff, which is the moderator role. **This block must not change the permission
   predicate** — it is phase 15 `AUTHZ-003`'s surface, and phase 15's validator explicitly
   did not re-file AD-001 because phase 04/05 owns the field set (§5.2).
5. **`transition_to`'s `refresh_from_db()` fights a form save.** The method's first
   statement re-reads from the database, so a sanctioned path through `transition_to` will
   discard the form's other unsaved field values unless the ordering is right. **The Planner
   must state the ordering**, and the Researcher must confirm whether a form save can safely
   route through a method that re-reads.
6. **Under option (b), `save_model` must not double-write.** If the service path already
   sets `published_at` and `original_published_at`, the form must not then write them
   again from its own fields. The four `search_vector*` fields are the same class of trap
   and are being removed.
7. **Ordering within the block.** The four unconditional fixes (audit row per Q1,
   `original_published_at` immutability, owner-transfer block, the two 500s) and the
   `search_vector*` removal are independent. Ship the **unconditional** ones first so the
   block makes progress even if Q1 takes time to be answered by the owner; the
   `status`-read-only change lands last and only under the answered option.
8. **Do not fix `VAL-003` here.** The gates were widened in BLOCK 3. If Q1 is option (a) or
   (b), BLOCK 6 touches `AdAdmin`; it does not touch `bulk_approve` or the review views.

**File surface (semantic units).**
- `src/backend/apps/ads/admin.py` → `class AdAdmin`: `readonly_fields`, the absence of
  `fields`/`fieldsets`/`exclude`/`form`, a new `save_model` override (option b/c), the
  `get_form`-level field contract, `actions` (read), `changelist_view` (read),
  `has_change_permission` / `has_view_permission` (**read only — phase 15 owns them**).
- **New (very likely):** a service module under `src/backend/apps/ads/services/` for the
  sanctioned admin lifecycle write, so the logic is not in a `ModelAdmin` method body
  (project rule 3). Named by the Planner; `apps/*` must not import `telegram_bot/*`.
- `src/backend/apps/moderation/services/moderation_log.py` → `set_published`, `set_rejected`
  — read only unless Q8 forces a new writer; the audit row must be written through the
  existing service so there is exactly one writer of `ModeratorActionLog` for a publish.
- `src/backend/apps/ads/models.py` → `Ad.transition_to` (read only, unless Q8 option ii is
  chosen).
- `src/backend/apps/ads/tests/` → a **new** change-form test module (e.g. alongside
  `test_ad_constraints.py` / `test_ad_lifecycle.py`, following the surrounding convention)
  and `test_ad_lifecycle.py::TestOriginalPublishedAtImmutability` (**keep green, do not
  edit**).
- Docs: `docs/04-user-stories/admin-stories.md` (US-A3 — **required under option (a)**, and
  **required under (b)** to record that the sanctioned seam is the service). **Never**
  `docs/01-spec/technical-specification.md` (phase 06).

**Tests required.**
- *Must be added* (a new change-form test module, all demonstrated **red** first):
  - A staff POST of `status=published` with a hand-picked `published_at` either (a) is
    refused, or (b) commits **with** a `ModeratorActionLog` row and an `AnalyticsEvent` —
    per the answered Q1. Assert the row count, not the absence of an exception.
  - `original_published_at` is **immutable** through the admin form.
  - `user` is **not** reassignable through the admin form.
  - A POST selecting `REJECTED` and one selecting `ON_MODERATION_FAILED` returns a
    **validation error**, not an HTTP 500. **This is a direct guard for violation 4 and is
    the one test in this block that can be written without Q1.**
  - `DELETED → published` through the form is refused.
  - The four `search_vector*` fields are **not** in the form's field list.
  - Under option (b): a status change made through the form writes exactly **one**
    `ModeratorActionLog` row and exactly **one** `AnalyticsEvent` — not two, not zero.
- *Must keep passing unchanged:* `test_ad_lifecycle.py::TestOriginalPublishedAtImmutability`
  (both cases) and `::TestPublishedAtUpdates`; `test_ad_constraints.py` in full;
  `test_transition_concurrency.py`; BLOCK 3's end-to-end approval tests;
  phase 04's `test_admin_pii_containment.py` (it covers `UserAdmin`, not `AdAdmin` — verify
  it is not affected).
- *Gate:* `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/ src/backend/apps/moderation/tests/ src/backend/apps/users/tests/test_admin_pii_containment.py" test`,
  then `.\Makefile.ps1 test`, then both static gates.

**Risk / rollback.**
- *Risk (the catastrophic one):* `status` → read-only lands while BLOCK 3 has not shipped,
  and moderators lose the ability to publish entirely. *Mitigation:* the hard `3 → 6` edge
  and note 7's internal ordering (the read-only change lands **last**).
- *Risk:* a save routed through `transition_to` silently discards the form's other field
  values, because `transition_to` starts with `refresh_from_db()`. *Mitigation:* note 5;
  the change-form tests assert on the *whole* saved row, not on one field.
- *Risk:* a double audit row or a double `AnalyticsEvent` under option (b). *Mitigation:*
  the "exactly one" assertions.
- *Risk:* an operator depends on reassigning an ad's owner through the form and loses the
  capability. *Mitigation:* this is violation 3, which is **unconditional**; if the owner
  disputes it, that dispute belongs to Q1, not to this block. Say so in the commit message.
- *Rollback:* the four unconditional fixes and the `status` read-only are **independently
  revertible**, and the block should be **structured as separate commits** so that a
  rollback of the read-only change does not take the 500 fixes with it.

---

### BLOCK 7 — Retention anchor, delete-sweep predicate, and the new partial index (AD-004, Q4, VAL-005)

| | |
|---|---|
| **Findings owned** | `05-AD-004`, and the `VAL-005` decision |
| **`depends_on`** | BLOCK 2 (soft — both touch the same retention story; BLOCK 2 must not assume an anchor) |
| **Priority** | P1 |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**This block is owner-gated (Q4) for its anchor half.** The *shape* of the fix (predicate,
index, or both) is a decision gate; the *anchor* is not the implementer's.

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- **Implementor — yes.** Always.
- **Auditor — yes.** Must re-read `delete_sweep.Command.handle`, `Ad.Meta.indexes` and all
  three disagreeing documents at the anchor, and must confirm at runtime that
  `GREATEST(published_at, archived_at)` is **not** directly expressible in a Django `Q`
  (the code context says it is not) and that no second query reads `archived_at`.
- **Researcher — yes.** This is the only block in the plan that must choose between three
  different query/index shapes with different write costs, on the hottest table in the
  system. The `GREATEST` branch requires two partial index-friendly branches, which changes
  the index story again.
- **Planner — yes.** A **schema migration**, a data-meaning change, a documentation
  reconciliation across three documents, and a hard prerequisite on a new partial index.
- **Validator — yes.** The change alters **what gets permanently deleted**. A wrong anchor
  either hard-deletes a seller's archived ad far too early (irreversible) or keeps it
  forever. Neither failure is visible in the suite.

#### 3.7.1 Owner gate — Q4 (the retention anchor)

**Three authoritative documents disagree, and the code matches the minority reading.**

| Source | Claim |
|---|---|
| `docs/02-database/db-retention.md` (the retention table and the sweep table) | `ARCHIVED` → **2 months from `archived_at`**; `delete_sweep` → *"Hard-delete ARCHIVED ads older than 60 days (from archived_at)"* |
| `docs/04-user-stories/seller-stories.md` US-S7 | *"2 months after last publish/edit → `ARCHIVED`; 4 months → permanently removed. Timers count from `published_at`"* |
| `docs/04-user-stories/admin-stories.md` US-A5 | *"archive @2 months, delete @4 months (from `published_at`)"* |
| `docs/01-spec/technical-specification.md` decision J | *"timers count from `published_at`"* — **phase 06 is editing this file; phase 05 must not** |
| The tree | `archive_sweep` = 60 d from `published_at`; `delete_sweep` = 60 d from `archived_at` |

**The two windows already agree numerically; only the anchor and the total lifetime
disagree.** Under the code's reading a *manual* archive is hard-deleted 60 days after the
click, so an ad published and archived on the same day is destroyed at +60 days from
publish instead of +120. Under the user stories' reading, **every** archive — manual or
automatic — is hard-deleted 4 months from `published_at`.

| Candidate anchor | Change | Pro | Con |
|---|---|---|---|
| **(i) `GREATEST(published_at, archived_at)`** | Select when **both** are older than the cutoff — i.e. the retention clock restarts at whichever is later. | Matches the report's independently-verified recommendation. Preserves the auto path exactly (the validator verified `archived_at − published_at = 61 days` resolves `GREATEST` to `archived_at`, so auto-archive still fires at `published_at + 120 d` = 4 months). Makes a manual archive's clock start at the click, which is what the seller experienced. | **Not expressible as a single Django `Q`.** The realistic shape is `Q(published_at__lt=cutoff) & Q(archived_at__lt=cutoff)`, or two branches — which **changes the index story again**, because a compound two-column condition cannot be served by a single-column partial index. Needs a **new** index, possibly a two-column one. |
| **(ii) `published_at` only** | Re-key the sweep on `published_at` and drop `archived_at` from the predicate entirely. | Simplest predicate; one new partial index on `(status, published_at) WHERE status='archived'` and the old index is simply removed. Matches US-S7/US-A5/decision J exactly. | A seller who **manually archives** a 3-year-old ad has it hard-deleted on the next run. That is a real seller-harm scenario and it must be stated to the owner as such. Also makes `archived_at` a write-only field for this sweep. |
| **(iii) `archived_at` only, but with a longer window** | Keep the current anchor and change 60 days → 120 days. | Zero predicate change, one constant change, no index change. | Contradicts US-S7's *"2 months after last publish/edit → ARCHIVED"* only in *total* lifetime terms. It is the **documentation-change** option: reconcile `db-retention.md` instead of the code. The cheapest fix, and it leaves the "manual archive is 60 days" complaint half-answered. |

**This is a documentation conflict as much as a code one.** The owner's answer determines
which document changes. The Planner must record, in the block's commit message, **which
document was reconciled and why**, so the next reader does not re-open it.

#### 3.7.2 Decision gate — the index (a hard prerequisite, not an optimisation)

The report's correction is confirmed in the tree: `IX_ads_delete_sweep` is
`(status, archived_at) WHERE status='archived'`. **Re-keying the sweep on `published_at`
silently drops that index**, and `delete_sweep` runs against the hottest table. A new
partial index is therefore **part of the fix**.

| Option | Change | Con |
|---|---|---|
| **A** | Add `IX_ads_delete_sweep_published` on `(status, published_at) WHERE status='archived'`; **remove** `IX_ads_delete_sweep`; migration does `RemoveIndex` + `AddIndex`. | Clean — one index for one predicate. On a large `ad_images`/`ads` table the migration takes an `ACCESS EXCLUSIVE` lock on `ads` briefly; it is a DDL-only migration, no table rewrite, and `CREATE INDEX CONCURRENTLY` is **not** available inside a Django `AddIndex` operation — the Planner must state the lock window and whether a separate `RunSQL` concurrent-index step is warranted. |
| **B** | Add the new index and **keep** the old one (unused). | Zero lock risk on the existing index. But leaves a dead index that costs write amplification on every `status` change and will confuse the next reader of `db-indexes.md`. |

**Either way, `docs/02-database/db-indexes.md` is a named DOC-UPDATE** — it documents
`IX_ads_delete_sweep` today and would be wrong afterwards.

#### 3.7.3 Decision gate — the row lock

`delete_sweep.Command.handle` has **no `select_for_update()`**, unlike `archive_sweep`
(which has it, with a `DB-010` comment explaining why). Adding one is a row-lock
acquisition on a queryset that is about to be hard-deleted. **Phase 03 BLOCK 7 (`03-DB-008`)
owns per-batch commits for this same command and must be re-read if it has landed** — two
phases restructuring one sweep is a merge hazard. Whether the lock is added here or deferred
to phase 03 is a Planner decision, recorded in the commit message either way. **The block
must not do phase 03's per-batch restructuring.**

**Findings and notes carried forward.**

1. **`IX_ads_archive_sweep` is already `(status, published_at) WHERE status='published'`**
   and `archive_sweep` already keys on `published_at`. So the project is *already
   inconsistent*: the auto path keys on `published_at`, the manual path's downstream sweep
   keys on `archived_at`. This block makes them agree, one way or the other.
2. **`test_sweep_lock_structure.py` asserts `session is False` for every lock-taking
   command.** Phase 03 BLOCK 2 requires that to stay satisfiable and so does this block. If
   a lock is added, it must be a **transaction-scoped** `advisory_lock` (already present) —
   the block adds no new lock id, and therefore **no new `AdvisoryLockId` member** (§5.3).
3. **`delete_sweep` collects `storage_keys` only to log `len(storage_keys)`.** Phase 03
   BLOCK 1 deletes that. **This block must not touch it** — the file is shared and the
   phases are sequential.
4. **A back-dated manual archive is the regression test.** Back-date a manually archived ad
   61 days and assert the sweep's selection behaviour **per the chosen anchor**; assert the
   **auto** path is unaffected (`archived_at − published_at` such that `published_at + 120 d`
   still fires). The validator independently verified the `GREATEST` branch preserves the
   auto path; that verification is **inherited** (U9) and must be re-run.
5. **The cosmetic documentation defect belongs here.**
   `docs/02-database/db-retention.md` contains the duplicated fragment *"`deleted_at` is
   older than `deleted_at` is older than 120 days"*. The report folds it into this block's
   file list. **Fix it here** — it is one line, it is in a file this block already edits, and
   fixing it anywhere else would be a second block for one sentence.
6. **The migration number is contested and must be re-read immediately before generation.**
   `src/backend/apps/ads/migrations/` currently ends at
   `0007_adimage_ix_adimages_image_and_more`, so `0008_*` is next — and **phase 03 BLOCK 6
   also claims `0008_*`** for `IX_ads_draft_sweep`. §5.3 states the serialisation rule.
   **The implementor must list the directory immediately before generating and take the
   next free number.** If phase 03 has already taken `0008`, this block takes `0009`; if
   this block takes `0008` first, phase 03 must be told. **Two migrations with the same
   number in one app is a hard failure, not a merge conflict.**
7. **No `print()`, no `AdvisoryLockId` change, no per-batch restructuring.**

**File surface (semantic units).**
- `src/backend/apps/core/management/commands/delete_sweep.py` → `Command.handle` (the
  cutoff, the filter, and — per the 3.7.3 decision — possibly `select_for_update`).
- `src/backend/apps/ads/models.py` → `Ad.Meta.indexes` → the `IX_ads_delete_sweep` entry
  (removed or kept, per the index decision).
- **New:** `src/backend/apps/ads/migrations/0008_<name>.py` (number re-read at generation
  time) doing the `RemoveIndex` + `AddIndex`.
- `src/backend/apps/core/tests/test_sweep_delete.py` and
  `src/backend/apps/core/tests/test_sweep_lock_structure.py` (**the latter's
  `session is False` assertion must stay satisfied**).
- Docs: `docs/02-database/db-retention.md` (**three** edits: the retention table row, the
  sweep table row, and the duplicated fragment), `docs/02-database/db-indexes.md` (the
  index entry), and the reconciled user story (`docs/04-user-stories/seller-stories.md`
  US-S7 and/or `admin-stories.md` US-A5, per the anchor decision).
- **Not touched:** `archive_sweep.py` (except a read to confirm the auto path),
  `docs/01-spec/technical-specification.md` (phase 06).

**Tests required.**
- *Must be added:*
  - A **manual** archive back-dated 61 days is selected / not selected **per the chosen
    anchor** — demonstrated **red** against the pre-fix code.
  - The **auto** path is unaffected: an ad whose `archived_at` is 61 days old but whose
    `published_at` is 119 days old is **not** deleted before `published_at + 120 d` under
    the anchor chosen (i.e. the "4 months from publish" promise holds).
  - A test that a long-lived archived ad (archived long after publication) is still
    eventually deleted — i.e. the chosen anchor did not create a permanent-archive hole.
  - A `delete_sweep --dry-run` case confirming the count and that nothing is written.
- *Must keep passing unchanged:* `test_sweep_delete.py::test_dry_run_does_not_delete` and
  every other case in that file; `test_sweep_lock_structure.py` in full (including the new
  command this block does **not** add); phase 03's `test_sweep_lock_structure.py` amendments
  if they have landed.
- *Gate:* **`.\Makefile.ps1 test-recreate` first** (new migration), then
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/ src/backend/apps/ads/tests/" test`,
  then `.\Makefile.ps1 test`, then both static gates.

**Risk / rollback.**
- *Risk (irreversible data loss):* the chosen anchor deletes a seller's archived ad earlier
  than the user stories promise. *Mitigation:* the auto-path test; the owner's explicit
  answer; the commit message records the answer.
- *Risk:* the new partial index is omitted and the sweep degrades to a sequential scan on
  the hottest table. *Mitigation:* the migration is a named deliverable and the index
  decision is a gate, not a nicety.
- *Risk:* `0008_*` collides with phase 03 BLOCK 6. *Mitigation:* re-read the directory
  immediately before generating (§5.3). **This is the most likely process failure in the
  block.**
- *Risk:* the migration takes a lock on `ads` long enough to stall the bot. *Mitigation:*
  3.7.2's `CONCURRENTLY` question; the DDL is index-only, not a table rewrite.
- *Risk:* `delete_sweep` is edited while phase 03's per-batch work is in flight. *Mitigation:*
  the hard `03-BLOCK-7 → this block` re-read rule (§5.2).
- *Rollback:* the migration reverses (`RemoveIndex` of the new, `AddIndex` of the old).
  **Rolling the migration back is safe; rolling back the predicate while keeping the index
  is harmless; rolling back the predicate and keeping the new index leaves a dead index.**
  Revert all three or none.

---

### BLOCK 8 — Editing a failed ad must not be a dead end (AD-002, Q5)

| | |
|---|---|
| **Findings owned** | `05-AD-002` |
| **`depends_on`** | BLOCK 1 (hard — the matrix must be a named value before an edge can be added to it) |
| **Priority** | P1 |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**This block is owner-gated (Q5).** The product rule for editing a failed ad is not the
implementer's to pick.

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- **Implementor — yes.** Always.
- **Auditor — yes.** Must re-derive, at the anchor, the **full** set of statuses the
  catch-all branch is reached by (**five**, not the two the report named) and must confirm
  the template renders the Edit link unconditionally. Both corrections are load-bearing for
  the allow-list's size.
- **Researcher — yes.** Q5 has three options with materially different product behaviour,
  and the code context points out that only one of them actually resets the purge timer.
- **Planner — yes.** The fix spans a view, a state-machine edge and a template, and it
  **rewrites a shipped green test**. It also has to decide where the "you cannot edit this"
  affordance lives, which is a UX question the report only partly answers.
- **Validator — yes.** HIGH severity, and the failure mode is a **seller losing work**: the
  current behaviour accepts the edit, tells them nothing, and the purge later reclaims the
  ad. A wrong fix either blocks a legitimate edit or keeps the silent loss.

#### 3.8.1 Owner gate — Q5 (what is the rule for editing a failed ad?)

| Option | Change | Pro | Con |
|---|---|---|---|
| **(a) Allow-list the direct-save branch** to exactly `DRAFT` and `ON_MODERATION`; return a clear error for everything else. | Smallest, most conservative. The branch is gated on an **explicit status set** rather than being a `catch-all`, which is the structural fix the report asks for. | Makes the branch's behaviour explicit and testable; every other status gets a defined answer instead of a silent write. | **Does not fix the dead end — it hides it.** `moderation_failed_at` is still not reset, so a `REJECTED` or `ON_MODERATION_FAILED` ad the seller could previously "edit" is now simply not editable. The seller is told, which is better, but the ad is still unrecoverable. |
| **(b) Add `ON_MODERATION_FAILED → ON_MODERATION` to the matrix and route through `submit_ad`** so the ad is re-moderated and `moderation_failed_at` is reset. | **The only option that actually resets the 7-day purge timer**, because `purge_failed_ads` keys on `moderation_failed_at`. It is also where `VAL-006` says the logic should live — one write path, one place. | Fixes the defect rather than the symptom. Gives the seller a real recovery path, which is the point of the feature. | **A deliberate loosening of a rule the state machine enforces on purpose.** The validator verified `ON_MODERATION_FAILED → PUBLISHED` is *correctly* refused; a seller could now resubmit content that just failed, repeatedly, and each attempt resets the purge timer — a potential "keep retrying forever" path that the 7-day timer was presumably there to bound. **The Researcher's design must state how the retry is bounded.** |
| **(c) Stop advertising the edit** for statuses where it cannot succeed. | Pure UI. No state-machine change. | Cheapest; removes a false affordance. | **Leaves the defect in place for any caller who POSTs directly**, and leaves the dead end in the API. A security-by-hiding change. Weak on its own. |

**The code context's reading is that (b) is the only option that fixes the purge timer, and
that if (a) or (c) is chosen the dead end is only hidden.** That is a **recommendation**,
not a decision, and the "seller retries forever" consequence of (b) is real. **This plan
does not choose.** The Planner must state, in the commit message, which option shipped and
**which consequence was accepted**.

**A structural fix applies under every option:** the `else:` catch-all must become an
**explicit status allow-list**. The report's scope correction is that the catch-all is
reached by **five** of the seven statuses — `DRAFT`, `ON_MODERATION`, `ON_MODERATION_FAILED`,
`REJECTED`, `DELETED` — and by `ARCHIVED` when the POST carries no `reactivate`. The
validator's instruction is explicit: *"The fix should gate the branch on an explicit status
allow-list rather than adding one more branch."* **Adding a sixth branch is forbidden.**

**Findings and notes carried forward.**

1. **A shipped green test asserts the `AD-002` catch-all and must change (project rule 2).**
   `apps/ads/tests/test_edit.py::TestEditOtherStatusDirectSave::test_edit_on_moderation_direct_save`
   — the docstring claims coverage of `ON_MODERATION` **and** `ON_MODERATION_FAILED` but
   only one test exists, and it asserts `ad.status == AdStatus.ON_MODERATION  # unchanged`.
   **Any allow-list or re-moderation fix breaks it.** It must be rewritten in this commit,
   with the reason recorded, and the misleading class docstring corrected so the next reader
   does not trust it.
2. **The defect's mechanism is the `update_fields` list.** The catch-all writes
   `["title", "description", "price_amount", "price_currency", "price_normalized_eur",
   "updated_at"]` — neither `status` nor `moderation_failed_at` is present. So the
   7-day `purge_failed_ads` timer is **not** reset and the rewritten content is reclaimed
   by the purge. This is statically derivable from the tree (U11) and the block must confirm
   it at runtime.
3. **"Just call the driver" is not available today.**
   `ALLOWED_TRANSITIONS[ON_MODERATION_FAILED] = {REJECTED}` — the report verifies the
   refusal. Under option (b) this block **adds the edge**; under (a) and (c) it does not,
   and the allow-list is what stops `submit_ad` being called on a refused transition.
4. **The template is part of the fix, not decoration.** `src/backend/templates/ads/dashboard.html`
   renders `<a href="{% url 'ads:edit' ad.id %}">{% trans "Edit" %}</a>` **unconditionally**
   for every ad in every status bucket. Under option (c) this is the whole change; under (a)
   and (b) the link should be gated on the statuses where edit can succeed, or the seller
   still clicks into a dead end. **Any new or moved string is an i18n obligation**
   (`ru` and `bs` non-empty).
5. **The view already owns one `atomic()` + `select_for_update()`.** Routing through
   `submit_ad` means a **nested** call inside that block, and `submit_ad` opens its own
   `atomic()` and re-fetches with `select_for_update()`. The Researcher must state the
   nesting depth and whether the re-fetch discards the form's pending values. This is the
   same interaction BLOCK 6's note 5 raises from the other direction.
6. **Do not touch the reactivation and text branches.** They already call `submit_ad` and
   they already render `errors[0]`. Their tests — `test_edit_published_text_edit_*` in
   particular, which BLOCK 2 also owns — must stay green unchanged.
7. **`VAL-006` constraint.** If Q1 is answered as option (b) and BLOCK 6 lands a single
   sanctioned write path, this block's fix has **exactly one place to live** and must be
   written there. If BLOCK 6 has not landed, this block writes the state-machine edge and
   the view branch, and BLOCK 6 must then adopt them. **Record which, in the commit
   message.**

**File surface (semantic units).**
- `src/backend/apps/ads/views/edit.py` → `ad_edit` (the `else:` catch-all branch, its
  `update_fields` list, and — under option (b) — the route into `submit_ad`).
- `src/backend/apps/ads/models.py` → the module-level `ALLOWED_TRANSITIONS` (**only** the
  `ON_MODERATION_FAILED` entry, and **only** under option (b)) and `Ad.transition_to`'s
  branch for the new target if one is added.
- `src/backend/apps/ads/services/submission.py` → `submit_ad` (read; only if the retry
  bounding from 3.8.1 lands there).
- `src/backend/apps/ads/tests/test_edit.py` → `class TestEditOtherStatusDirectSave`
  (**rewrite**) and `class TestPublishedTextEdit` (**do not touch** — BLOCK 2's).
- `src/backend/templates/ads/dashboard.html` → the unconditional Edit link.
- `src/backend/apps/ads/tests/test_submission.py` → read; must stay green.
- Docs: `docs/04-user-stories/seller-stories.md` (US-S2 / the edit affordance, if the owner
  answer changes the promise). **Never** `technical-specification.md` (phase 06).

**Tests required.**
- *Must be **rewritten**:* `TestEditOtherStatusDirectSave::test_edit_on_moderation_direct_save`
  — both the assertion and the class docstring, with a comment recording that the test
  encoded the defect. (Project rule 2: production code is king.)
- *Must be added:*
  - Under option (a)/(c): a POST to an ad in a non-allow-listed status is **refused** with
    an actionable message and the ad is **unchanged** — demonstrated **red** before the fix.
  - Under option (b): editing a failed ad **re-moderates** it; `moderation_failed_at` is
    reset; the status leaves `ON_MODERATION_FAILED`; `purge_failed_ads` does **not** reclaim
    the rewritten content. This is the direct regression guard and it is the only test that
    proves the finding is fixed rather than hidden.
  - Under option (b): the retry bounding from 3.8.1 — repeated failed resubmissions do not
    extend the ad's life **indefinitely**.
  - The **five-status** reachability of the catch-all is now explicitly encoded: a test
    enumerating each of `DRAFT`, `ON_MODERATION`, `ON_MODERATION_FAILED`, `REJECTED`,
    `DELETED` and asserting the *defined* outcome for each. This is the structural fix's
    guard — a future `else:` re-broadening fails it.
  - The dashboard Edit link is present exactly for the statuses where edit can succeed.
- *Must keep passing unchanged:* `TestPublishedTextEdit` in full (BLOCK 2's);
  `test_submission.py` in full; `test_ad_lifecycle.py`;
  `test_i18n_completeness.py` and `test_i18n_pipeline.py`.
- *Gate:*
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/" test`,
  then `.\Makefile.ps1 test`, then both static gates.

**Risk / rollback.**
- *Risk (seller data loss, the finding itself):* option (a) or (c) ships and the ad is
  still purged, only now with a message. *Mitigation:* the "must not reset
  `moderation_failed_at` is **not** a fix" note is in the gate table; the commit message
  must state which consequence was accepted.
- *Risk (abuse):* option (b) lets a seller retry forever. *Mitigation:* the bounding design
  and its test are **part of the option**, not optional.
- *Risk:* the `else:` catch-all is left in place with one more `if` added — the exact
  thing the validator forbade. *Mitigation:* the five-status enumeration test.
- *Risk:* a rewrite of `test_edit_on_moderation_direct_save` that keeps the old assertion
  shape and simply changes the expected status. *Mitigation:* the test must be red first.
- *Rollback:* one commit, no migration. Revert restores the silent dead end.

---

### BLOCK 9 — The bulk-moderation endpoint needs a transaction, a lock and honest errors (AD-010, Q11)

| | |
|---|---|
| **Findings owned** | `05-AD-010` (the **narrow** form only) |
| **`depends_on`** | BLOCK 3 (soft — same subsystem, shared status semantics) |
| **Priority** | P2 |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- **Implementor — yes.** Always.
- **Auditor — yes.** Must re-derive the endpoint's actual shape at the anchor and confirm
  the report's struck claims are still absent (no `ban` branch, a `BulkModerationAction`
  `StrEnum`, service delegation) — otherwise a future implementor re-introduces the
  refuted "delete the loop and call `bulk_approve`" recommendation.
- **Researcher — yes.** Q11 is a genuine transaction-shape question with a response-contract
  conflict at its centre, and the error-string question has an information-disclosure
  dimension.
- **Planner — yes.** A change to an HTTP endpoint's transaction boundary and its response
  contract, with four shipped test classes depending on both.
- **Validator — yes.** The block touches a **moderation write path**. A wrong transaction
  shape turns a per-ad failure into a batch abort (or the reverse), and neither failure is
  visible without a test that mixes a good id with a bad one.

#### 3.9.1 Decision gate — Q11 (transaction shape, and what the error may say)

| Option | Change | Pro | Con |
|---|---|---|---|
| **A — per-request `atomic()`** | Wrap the whole loop in one `transaction.atomic()`. | One line; consistent with `bulk_approve`'s shape. | **Contradicts the endpoint's own response contract.** `{"completed": N, "errors": [...]}` promises partial success. An all-or-nothing batch either discards successful work or must special-case the rollback, and a batch of 100 that fails on ad 27 does 99 units of work for nothing. |
| **B — per-ad `atomic()` + `select_for_update()`** | Each iteration gets its own transaction and row lock, matching `review.py`'s per-ad view pattern. | **Preserves the current per-ad error isolation**, which is what the response shape already promises. Makes each ad individually consistent (it partly is today via the services' internal `atomic()`). | N transactions for N ads — but the endpoint is capped at `MAX_BULK_ACTIONS = 100`, so the cost is bounded and the lock is acquired on one row at a time. Requires the loop body to be restructured, not just wrapped. |
| **C — bulk `QuerySet` rewrite** | Re-derive the queryset once, lock it, and delegate to `bulk_approve` / `bulk_reject`. | Efficient; one query. | **Unexecutable as the report framed it** — but a *correct* version is possible only after BLOCK 3 has made those functions do anything, and it changes the endpoint's semantics from "these ids" to "this queryset". Overreach for a MEDIUM finding. |

**The code context's framing of A contradicts the response shape; B preserves it. This plan
records the trade-off and does not choose** — the Planner must, in the block's task
`extra_context` and in the commit message.

**The error-string question, which is part of Q11 and is not free.** The current code logs
`logger.error("Bulk moderation failed for ad %s: %s", ad_id, e)` and returns
`{"id": ad_id, "error": "Processing failed"}` with **HTTP 200**. Two problems: a state-machine
`ValueError` is logged at **ERROR** on **ordinary user input**, and the operator gets a
cause-free message. The fix must make the returned string **actionable without leaking
internals** — the same `AD-012` CWE-209 discipline, one layer up. A `ValueError` from the
state machine is a *user* error (an invalid transition) and should be a **4xx-class outcome
per id, at `WARNING`**, not a swallowed 200 at `ERROR`. Any genuinely unexpected exception
should keep the generic string at `ERROR` **and** be distinguishable in the response (an
`ok`/`retryable` field, or an error-code enum — not free text).

**Findings and notes carried forward.**

1. **The report's root cause and recommendation are struck and must stay struck.** There is
   no duplicated implementation — the endpoint already imports `approve_ad` / `reject_ad`
   from `apps.moderation.admin_actions` (verified at runtime by the validator: the
   functions' `__module__` is `apps.moderation.admin_actions`). `bulk_approve` takes a
   `QuerySet`, not an id list, so *"call `bulk_approve`"* is unexecutable.
2. **The `StrEnum` is already correct.** `BulkModerationAction` is exactly
   `['approve', 'reject', 'flag']`, compared by enum identity. **There is no `ban` branch**
   and there must not be one added here — `bulk_ban_users` is a separate path with a phase-04
   tripwire.
3. **The `FLAG` branch is the one with no transaction at all.**
   `PriorityService().calculate_and_save(ad)` runs outside any transaction. Under Option B it
   gets one; under Option A it inherits the batch's. Either is an improvement; the block must
   state which it got.
4. **Per-ad consistency partly exists today.** `approve_ad` / `reject_ad` open their own
   nested `atomic()` internally via `set_published` / `set_rejected`. So each ad is
   individually consistent and the **batch** is not. The block's job is the batch.
5. **Two source-inspection guards constrain the fix's shape.**
   `TestBulkLockingStructure::test_bulk_approve_uses_select_for_update_orderby_atomic`
   asserts `"select_for_update"`, `"order_by"` and `"pk"` all appear in
   `inspect.getsource(bulk_approve)` — **this block must not edit `bulk_approve`**, so the
   guard is unaffected; but if the design moves the loop into a helper, the guard's assumption
   about *where* the locking lives must be re-checked. And phase 04's
   `test_bulk_ban_users_not_locked` asserts `select_for_update` is **not** issued on the
   bulk-**ban** path — **adding a lock must not touch `bulk_ban_users`.**
6. **This block must not route the endpoint through `auto_moderate`** (same prohibition as
   BLOCK 3/6: it would re-apply automatic criteria over a moderator's decision).
7. **`Pydantic v2` boundary is unchanged.** `BulkModerationRequest.model_validate_json` and
   the `422` + `pydantic_errors_json` path are correct and out of scope. The
   `MAX_BULK_ACTIONS` bound is correct and out of scope. **Do not widen it.**
8. **The response shape is a public contract.** Whatever Option B does, the
   `{"completed": N, "errors": [...]}` shape must be preserved or the change must be
   deliberate and recorded. Consumers of this endpoint are outside the repository, so
   **the Planner must state who consumes it before changing its shape** — and the default
   answer is *do not change it*.

**File surface (semantic units).**
- `src/backend/apps/moderation/views/api_bulk.py` → `bulk_moderation_action` (the loop, the
  `Ad.objects.get`, the three branches, the `except Exception`), and `MAX_BULK_ACTIONS`
  (**read only**).
- `src/backend/apps/moderation/admin_actions.py` → `approve_ad`, `reject_ad` — **read
  only**. `bulk_approve`, `bulk_reject`, `bulk_ban_users`, `bulk_delete`, `soft_delete_ad`
  — **read only**. This block changes the **endpoint**, not the services.
- `src/backend/apps/moderation/services/priority.py` → `PriorityService.calculate_and_save`
  (read; the block states which transaction it now runs in).
- `src/backend/apps/moderation/tests/` → the endpoint's own test module, plus
  `test_admin_actions.py::class TestBulkOperations` (**keep green; do not edit**).

**Tests required.**
- *Must be added:*
  - A batch mixing a **valid** id with an id in an **invalid status**: the valid ad is
    processed, the invalid one is reported, and the response is still **200** with the
    expected `completed` count — i.e. the partial-failure contract is preserved under the
    chosen option. **This is the test that distinguishes Option A from Option B**, and it
    must be demonstrated **red** for Option A before the fix.
  - A `ValueError` from the state machine is **not** logged at `ERROR` and is not reported
    as a cause-free "Processing failed".
  - The response's error string contains **no** raw driver text — the same discipline as
    BLOCK 11.
  - Under Option B: an `IntegrityError` raised while processing ad *k* leaves ad *k*
    untouched and does **not** roll back ads 1..*k*−1.
  - A genuinely unexpected exception still produces a generic, non-leaking string and an
    `ERROR`-level log — the fix must not turn an infra failure into a silent 200 either.
- *Must keep passing unchanged:*
  `TestBulkLockingStructure::test_bulk_approve_uses_select_for_update_orderby_atomic`;
  `test_bulk_ban_users_not_locked` (phase 04); the `422` / `MAX_BULK_ACTIONS` cases; the
  existing endpoint happy-path tests.
- *Gate:*
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/moderation/tests/" test`,
  then `.\Makefile.ps1 test`, then both static gates.

**Risk / rollback.**
- *Risk:* Option A silently makes every bulk moderation call all-or-nothing while the
  response still says "completed 97 of 100". *Mitigation:* the mixed-batch test is
  mandatory and Option A must fail it.
- *Risk:* an error string is made "actionable" by interpolating the exception — the
  `AD-012` defect, one layer up. *Mitigation:* the "no raw driver text" assertion.
- *Risk:* the fix re-adds a lock to the bulk-**ban** path and reds phase 04's tripwire.
  *Mitigation:* note 5.
- *Rollback:* one commit, no migration, no schema. Clean revert.

---

### BLOCK 10 — `AdImage.position` needs a uniqueness constraint (AD-014, Q9)

| | |
|---|---|
| **Findings owned** | `05-AD-014` |
| **`depends_on`** | BLOCK 7 (soft — **both take the next free `apps/ads` migration number**; serialise the numbers) |
| **Priority** | P2 |
| **Roster** | **Implementor, Auditor, Planner, Validator** → *not* all five |

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — yes.** Owns the **Q9 data pre-flight** (note 3), which cannot be answered by
  reasoning — only by a query. This is the one thing in the block that can make the migration
  fail.
- **Researcher — no.** The shape is fully determined: a uniqueness-only constraint. The
  contiguity question is explicitly answered by shipped, asserted behaviour (note 2), and
  the maintainability/future-evolution trade-off is a two-line one. A Researcher pass would
  add latency and no information.
- **Planner — yes.** Two blocks in this plan take a migration number, and this is the second
  one. A wrong number is a hard failure. The Planner must also sequence the **backfill**
  if Q9 finds duplicates.
- **Validator — yes.** A schema change on a table that every ad render joins. The failure
  mode is a migration that fails halfway on a production-shaped dataset.

#### 3.10.1 Owner gate — Q9 (do duplicate `(ad, position)` rows exist?)

**This is a data fact and it is not answerable from the code.** `AddConstraint` fails on a
table that already violates it, and the report's severity note says the invariant *"holds
today only because the sole production writer derives positions from a list"*.

**Mandatory pre-flight, before any migration is written:**

```sql
SELECT ad_id, position, COUNT(*)
FROM ad_images
GROUP BY ad_id, position
HAVING COUNT(*) > 1;
```

The code context is explicit that this **must be run against a copy of production-shaped
data, not the test database** — the test database is seeded by `load_catalog`/`seed` and
will not exercise the paths that could produce a duplicate. The Auditor owns this step, and
its result is recorded in the block's task `extra_context` and in the commit message.

| Result | Action |
|---|---|
| **No rows** | Straight `AddConstraint` migration. No backfill. |
| **Rows found** | A **data migration must run first** (re-number positions per ad), then the constraint. The re-numbering rule must be stated explicitly — a deterministic, documented ordering (e.g. by `id` within each ad) — and the migration must be a single `AddConstraint` following it, so a partial run is visible. **This roughly doubles the block's size and its risk.** |

#### 3.10.2 The constraint is uniqueness-only. Contiguity is **forbidden**.

`test_copy_ad.py::test_copy_ad_image_positions_preserved` deliberately uses positions
**`[0, 2, 5]`** — **gaps are a shipped, asserted behaviour**. Adding a contiguity constraint
would break a green test that is asserting something the project intends, and the report
recommends documenting gaps as permitted. The `AdImage.Meta.docstring` or the model comment
must say so explicitly, so the next reader does not "helpfully" close the gaps.

**Findings and notes carried forward.**

1. **`unique_together` is one shape; a `UniqueConstraint` is the other.** Project rule 10 and
   the surrounding `Meta` (which already uses four `CheckConstraint`s) favour
   `models.UniqueConstraint(fields=["ad", "position"], name="uq_ad_images_ad_position")` —
   a **named** constraint, which is what the `AddConstraint` migration and the error message
   will reference. `unique_together` produces an unnamed index. **The Planner must choose
   and state which**, and the name must be recorded in `docs/02-database/db-indexes.md`.
2. **`copy_ad` is a second `position` writer** and copies `position=img.position` verbatim
   — so it cannot introduce a duplicate **within** one ad, but nothing stops
   `AdImage.objects.create(ad=ad, position=0)` twice. The constraint removes that class of
   bug; it does not fix a current one.
3. **The pre-flight must be against production-shaped data** (note above). A `--create-db`
   run with the standard fixtures will **not** exercise the duplicate-producing paths, so a
   green `test-recreate` is **not** evidence that the migration is safe on real data.
4. **The migration number is the second claim on `apps/ads`.** BLOCK 7 also generates one.
   **The safe serial order is BLOCK 7 → BLOCK 10**, and §4.1 records the edge. The
   implementor must list `src/backend/apps/ads/migrations/` immediately before generating and
   take the next free number. **Two migrations with the same number in one app is a hard
   failure.**
5. **`AdImage.Meta.indexes` already has four single-column indexes.** The new unique
   constraint creates a **fifth** index on the same table. That is a deliberate write-cost
   increase on photo insert — acceptable, because `AdImage` rows are created in bursts during
   submission and are never updated in the hot path. The Planner should state the trade-off
   rather than discover it.
6. **This block must not touch the media layer.** The storage-key ownership model is phase
   07's (`MEDIA-001`), and `AdImage.save`'s SHA-256 hook is phase 03 BLOCK 8's (§5.2).

**File surface (semantic units).**
- `src/backend/apps/ads/models.py` → `class AdImage` → `class Meta` (the new
  `UniqueConstraint`, the gaps-are-permitted comment) and the model docstring.
- **New:** `src/backend/apps/ads/migrations/0009_<name>.py` (number re-read at generation
  time; `0008` is BLOCK 7's if BLOCK 7 has already landed) — `AddConstraint`, and
  `RunPython` **only if** Q9 finds duplicates.
- `src/backend/apps/ads/tests/test_copy_ad.py` → `::test_copy_ad_image_positions_preserved`
  (**must keep passing unchanged** — it is the guard that contiguity was not added).
- Docs: `docs/02-database/db-indexes.md` (the new constraint), and the gaps note.

**Tests required.**
- *Must be added:*
  - A test that creating two `AdImage` rows for the same ad at the same position raises
    `IntegrityError` — demonstrated **red** against the pre-fix schema.
  - A test that the **same position on a different ad** is allowed (the constraint is
    `(ad, position)`, not `(position)`) — this is the case a careless implementation gets
    wrong.
  - If Q9 found duplicates and a data migration is added: a test that the data migration
    re-numbers deterministically and that the constraint then applies.
- *Must keep passing unchanged:* `test_copy_ad.py::test_copy_ad_image_positions_preserved`
  (positions `[0, 2, 5]` — **the contiguity guard**); `test_adimage_storage_keys.py`;
  `test_gallery_markup.py`; every `apps/media` test.
- *Gate:* **`.\Makefile.ps1 test-recreate` first** (new migration), then
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/ src/backend/apps/media/tests/" test`,
  then `.\Makefile.ps1 test`, then both static gates.

**Risk / rollback.**
- *Risk (hard failure):* `AddConstraint` fails on real data because the pre-flight was run
  against the test database. *Mitigation:* the pre-flight is a **hard gate** and must be
  against production-shaped data; the commit message records the query and its result.
- *Risk:* a contiguity constraint is added "while in there" and breaks the shipped
  `[0, 2, 5]` test. *Mitigation:* the test is named as the guard; the model comment records
  that gaps are permitted.
- *Risk:* the migration number collides with BLOCK 7's. *Mitigation:* the `7 → 10` ordering
  edge and the re-read rule.
- *Risk:* a fifth index on `ad_images` degrades submission throughput. *Mitigation:*
  measured, not assumed — the block states the trade-off; the write is bursty and not in the
  hot read path.
- *Rollback:* `RemoveConstraint` reverses cleanly. If a data migration ran, **the rollback
  does not restore the original positions** — the re-numbering is lossy in the reverse
  direction. That must be stated in the block before shipping.

---

### BLOCK 11 — `ad_copy` must not render a raw driver error into a seller's chat (AD-012, bot half)

| | |
|---|---|
| **Findings owned** | `05-AD-012` — **the CWE-209 bot half only** |
| **`depends_on`** | — (but **after** phase 03 BLOCK 10 — §5.3) |
| **Priority** | P2 |
| **Roster** | **Implementor, Auditor, Planner, Validator** → *not* all five |

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — yes.** Must confirm at the anchor that `copy_ad` still does **not** set
  `status=` explicitly and does not handle `uq_ads_single_draft_per_user`, so this block
  stays on the bot side of the boundary and does not drift into phase 03's territory.
- **Researcher — no.** The finding is a well-understood information-disclosure defect with
  one obvious remedy. There is no architectural question and no modern-practice question.
- **Planner — yes.** It needs a **new user-visible string set** with three locales and a
  decision about which exception classes map to which message — and the i18n obligation
  makes that a real deliverable rather than a one-liner.
- **Validator — yes.** The block's whole point is that a specific string must never reach a
  user; the verification is "assert the absence of raw driver text", which is a subtle thing
  to get right.

**Scope: the bot half only.** The single-`DRAFT`-invariant half of `AD-012` is
`03-DB-009` (phase 03 BLOCK 10), including the product decision of whether a new draft
replaces the current one or a second draft is rejected with a message. **This block must not
touch `copy_ad`'s draft handling**, and phase 03's fix must land first so this block does not
ship a message for a condition whose rule is still undecided (§5.3).

**Findings and notes carried forward.**

1. **The current code is a textbook CWE-209.** The `except Exception as e` branch calls
   `logger.exception(...)` — correct — and then
   `_("Failed to copy ad: {error}").format(error=e)` with `e` being the psycopg
   `IntegrityError`, whose text contains the table name, the constraint name
   `uq_ads_single_draft_per_user`, and `DETAIL: Key (user_id)=(6) already exists.`
2. **The i18n shape is part of the defect.** `_()` is applied to the **template** before
   `.format`, so the whole interpolated sentence is a single translated unit. A
   translator is being asked to translate a sentence with a slot that will contain a
   PostgreSQL error, and the resulting string is both untranslatable in practice and
   un-actionable for a seller. **The fix must move the error out of the translated string
   entirely** — the user-visible text is a fixed, translated sentence; the technical detail
   goes to the log.
3. **The same `except Exception` collapses three distinct conditions**: `Ad.DoesNotExist`
   (the ad was deleted), a permission error that is not exactly `PermissionError`, and the
   constraint violation. The fix must catch the specific conditions and produce a specific,
   actionable message for each — and the `PermissionError` case already has a correct
   message that must be preserved exactly.
4. **The message for the constraint case is a phase-03 deliverable.** Phase 03 BLOCK 10
   decides the single-draft rule, and BLOCK 6 of that plan "ships a seller-facing message for
   the expired-draft case" — that is `AD-016`'s neighbour. **One message per condition:**
   this block must **reuse** phase 03's string for the draft-exists case if phase 03 has
   landed, and must not invent a second one for the same condition (§5.3).
5. **New user-visible strings need non-empty `msgstr` for `ru` *and* `bs`;** `en` may be
   empty. Gated by `test_i18n_completeness.py` and `test_i18n_pipeline.py`.
6. **`_()` in this file is `gettext_lazy`-style usage from aiogram's translation helper.**
   The block must follow whatever the file already uses and must not switch translation
   mechanisms.

**File surface (semantic units).**
- `src/telegram_bot/handlers/ad_copy.py` → `cmd_copy` (the `except PermissionError` branch
  and the `except Exception` branch).
- `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` — **append only** (§5.3).
- **Not touched:** `src/backend/apps/ads/services/copy_service.py::copy_ad` (phase 03
  BLOCK 10's surface), `src/backend/apps/ads/tests/test_copy_ad.py` (read only — must stay
  green).

**Tests required.**
- *Must be added:*
  - A test that the failure reply contains **no** raw driver text — asserted over
    constraint name, table name, `DETAIL` and `CONTEXT` substrings. This is the direct
    guard and it must be **red** against the pre-fix code.
  - A test per condition: ad-not-found, permission-denied, draft-exists — each producing a
    **distinct, translated** message.
  - A test that the **log** still carries the technical detail (so the fix does not simply
    delete the diagnostics).
  - A test that the permission-denied message is byte-identical to today's.
- *Must keep passing unchanged:* `apps/ads/tests/test_copy_ad.py` in full — including
  `::test_copy_ad_happy_path`, which asserts the storage-key aliasing that **phase 07
  rules is legal**. **This block must not touch it** (that is phase 07's test budget); and
  `telegram_bot` handler tests for `ad_copy`.
- *Gate:*
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/telegram_bot/tests/ src/backend/apps/ads/tests/test_copy_ad.py" test`,
  then `.\Makefile.ps1 test`, then both static gates.

**Risk / rollback.**
- *Risk:* "fixing" the message by moving the exception into a log-only path and returning a
  generic string loses the seller's ability to act. *Mitigation:* the per-condition tests.
- *Risk:* two messages for the draft-exists condition, because phase 03's string lands
  after this block. *Mitigation:* the hard ordering against phase 03 BLOCK 10, and the
  "one message per condition" rule.
- *Risk:* the `.po` files are regenerated wholesale and a concurrent phase's additions are
  discarded. *Mitigation:* **append only** (§5.3).
- *Rollback:* one commit, no migration. Clean revert; the reverts to a CWE-209 defect.

---

### BLOCK 12 — An expired draft is not a moderation failure (AD-016, Q12, Q7)

| | |
|---|---|
| **Findings owned** | `05-AD-016` — the **distinguishable-return** and **non-destructive-FSM** halves |
| **`depends_on`** | BLOCK 5 (soft — same function; see 3.12.1) · **phase 03 BLOCK 6 must be re-read** |
| **Priority** | P2 |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Agent requirement decision (the "high risk ⇒ all agents" rule applies here).**
- **Implementor — yes.** Always.
- **Auditor — yes.** Must enumerate **all** `submit_ad` callers and state for each whether it
  consumes the `errors` list. The code context already establishes that `ad_edit`'s
  reactivation and text branches render `errors[0]` while the bot **discards** it — so a
  return-type change has a different blast radius at each call site and the Auditor must
  confirm it at the anchor.
- **Researcher — yes.** Q12 (what "distinguishable" means in a `tuple[bool, list[str]]`) and
  Q7 (whether a *system* error may be reported as a content verdict) are both genuine, and
  the code context raises Q7 as a scope question.
- **Planner — yes.** A **return-type contract** change across three call sites in two
  packages, a **user-visible string**, and a decision about what the bot does with FSM state
  on a non-content failure.
- **Validator — yes.** The failure mode is *silent work destruction*: the seller types for
  ten minutes, the draft is swept, and the bot tells them their content failed and clears
  their state. A regression here is invisible to every test that does not simulate a
  swept draft.

#### 3.12.1 Decision gate — Q12 (what "distinguishable" means)

| Option | Change | Pro | Con |
|---|---|---|---|
| **A — a typed outcome** | Introduce a small result type (a `StrEnum` outcome member plus the existing `list[str]`), e.g. a `SubmitAdOutcome` `StrEnum` returned alongside. Fits project rule 10 and Pydantic-v2-at-boundaries. | Explicit, greppable, translatable (one key per outcome). The bot renders by outcome; `ad_edit` keeps rendering `errors[0]`. | Touches **every** caller. All three call sites change. The type must be importable from both `apps.ads` and `telegram_bot` (it lives in `apps/ads`, and `telegram_bot` importing from `apps` is the allowed direction). |
| **B — a sentinel error string** | Return a distinguished, machine-comparable string in the existing `errors` list, e.g. a module-level constant the bot compares against. | Zero caller churn beyond the bot. | **Fragile**: the string crosses a translation boundary and a `StrEnum`-less constant is exactly the kind of "fixed value as a string" project rule 10 forbids. It is also a *string comparison* in a hot path. The code context calls this out as fragile. |
| **C — widen the return type** | Change `tuple[bool, list[str]]` to a richer result object carrying `ok`, `outcome` and `errors`. | Cleanest to consume; the bot can switch on it. | The largest churn: `process_preview` and both `ad_edit` branches change, plus every test that asserts on the tuple shape. Given this is a MEDIUM finding, this may be overreach. |

**The code context's implicit preference is A or C over B. This plan does not choose** — the
Planner must, and must record the caller inventory that motivated the choice.

#### 3.12.2 Decision gate — Q7 (scope: is a system error reported as a content verdict a phase-05 finding?)

`auto_moderation.py` → `_pass_moderation` catches `MaxAdsExceeded` **and** a bare
`except Exception`, and on any exception calls `_fail_moderation(ad)` and returns `False`.
So a **database error during publish** is reported to the seller as *"Ad failed moderation.
Please check your content and try again."* — a system failure is converted into a content
verdict.

**This is the same defect class as `AD-016`, in a different file, and it is not in the
source report's scope.** Q7 is a scope decision routed to the coordinator: fold it into this
block as an extra branch, file it as a new finding owned by phase 03 (transaction-error
classification), or defer it.

**Q7 is deliberately a non-blocking gate.** BLOCK 12 ships whether or not it is answered.
Its only effect is the size of the block. **The commit message must record the Q7 disposition
either way**, so the decision is not silently dropped.

#### 3.12.3 What belongs to phase 03, and what belongs here

| Concern | Owner |
|---|---|
| The `sweep_drafts` predicate (`created_at` → idle `updated_at` + heartbeat), the `ads/0008_*` migration, `IX_ads_draft_sweep`, and the seller-facing "your draft expired" **message** | **Phase 03 BLOCK 6** (`03-DB-003`) |
| `submit_ad` returning a **distinguishable** result for "draft no longer exists" | **Phase 05 — BLOCK 12** |
| `process_preview` **not destroying the FSM state** on a non-content failure | **Phase 05 — BLOCK 12** |
| The bot's rendering of that outcome | **Phase 05 — BLOCK 12**, **reusing phase 03's string** |

**Rule: one message per condition.** If phase 03's BLOCK 6 has already shipped an
expired-draft string, this block **must reuse it** and must not add a second one for the
same condition. If phase 03 has **not** landed, this block reuses the `msgid` phase 03
declared and does **not** invent wording. **This block must not ship a draft-lifetime
change** (§5.3).

**Findings and notes carried forward.**

1. **Two returns are indistinguishable today.** `submit_ad` returns
   `(False, ["Ad not found"])` on `Ad.DoesNotExist` and `(False, ["Ad failed moderation
   checks"])` on a moderation failure — same shape, different causes.
2. **The bot discards the reason entirely.** `process_preview` renders a **fixed** message
   for every non-success and then calls `await state.clear()`. So even if `submit_ad`
   returned a distinguishable value today, the bot would not use it. **Both halves must
   change together**, which is why they are one block.
3. **`state.clear()` is the work destruction.** After it, the seller cannot retry at all —
   not "retry and lose one step", but "start over". Under a sweep, the draft is already
   gone, so the FSM data is the only remaining copy. **Clearing it is strictly harmful in
   this case.** The fix must not clear the state when the outcome is "your draft expired";
   it may still clear it on a genuine content failure (the seller should start a new ad
   either way).
4. **A third non-success cause exists and is the code context's own addition:** the
   translation layer itself failing. The report names three — content failed, the draft was
   swept, the translation layer failed. A fourth arrives with Q7: a **system** error. The
   outcome enum must have a home for each, or the same conflation returns.
5. **`ad_edit`'s two `submit_ad` branches already render `errors[0]`** — they *do* consume
   the list. So a return-type change has an **asymmetric** blast radius: the bot must be
   rewritten, the web view mostly will not. The Auditor's caller inventory must state this
   before the type changes.
6. **The gap in coverage is where the fix lands.** No test covers `submit_ad`'s
   `(False, ["Ad not found"])` return, and no bot test covers `process_preview`'s failure
   branch. **Both are gaps and both must be filled by this block.**
7. **New user-visible strings need non-empty `ru` *and* `bs` `msgstr`.** Append only (§5.3).

**File surface (semantic units).**
- `src/backend/apps/ads/services/submission.py` → `submit_ad` (the `Ad.DoesNotExist`
  branch, the return contract, and the module's type annotations) and, if Option A/C is
  chosen, a **new** outcome `StrEnum` in the same package (project rule 10) re-exported
  through its `__init__.py` and `__all__`.
- `src/telegram_bot/handlers/ad_create/submit.py` → `process_preview` (the `else` branch: the
  fixed message and the `await state.clear()`).
- `src/backend/apps/ads/views/edit.py` → `ad_edit` (the two `submit_ad` branches — **read and
  confirm**, change only if the chosen return type requires it).
- `src/backend/apps/ads/tests/test_submission.py` → the two named cases in the "keep green"
  list; the `(False, ["Ad not found"])` gap.
- `src/telegram_bot/tests/` → a bot-level test for `process_preview`'s failure branch (there
  is none today).
- `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` — **append only**, and **only** if
  the chosen option needs a new key that phase 03 has not already declared.
- **Not touched:** `sweep_drafts.py`, `IX_ads_draft_sweep`, any draft-lifetime constant.

**Tests required.**
- *Must be added:*
  - `submit_ad` against a **deleted** draft returns the **expired-draft outcome**, and it is
    **distinguishable** from a moderation failure — demonstrated **red** before the fix.
  - The bot renders a **translated, seller-recoverable** message for the expired-draft case
    — the message tells the seller to run `/post` again, and does **not** blame their
    content.
  - `process_preview` **does not clear the FSM state** for the expired-draft outcome.
  - A genuine content failure still clears the state and still renders the moderation
    message — the fix must not make the bot non-recoverable in the other direction.
  - If Q7 is folded in: a **system** error during `_pass_moderation` is **not** reported as
    a content verdict, and `MaxAdsExceeded` remains distinguishable from a generic error.
- *Must keep passing unchanged:* `test_submission.py::test_submit_ad_rolls_back_when_auto_moderate_raises`
  and `::test_submit_ad_commit_when_auto_moderate_passes` (**note:** if BLOCK 5 option (i)
  has landed, the first one's name is already wrong and BLOCK 5 rewrote it — **BLOCK 12
  must re-read, not assume**); `test_edit.py` in full (BLOCKs 2 and 8's);
  `test_i18n_completeness.py` and `test_i18n_pipeline.py`.
- *Gate:*
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/ src/telegram_bot/tests/" test`,
  then `.\Makefile.ps1 test`, then both static gates.

**Risk / rollback.**
- *Risk:* the return-type change breaks a caller the inventory missed, and the failure is a
  `TypeError` in production. *Mitigation:* the mandatory caller inventory; the type must be
  introduced and consumed in **one** commit, never half-way.
- *Risk:* the state is no longer cleared, and a stale FSM context lingers into the next
  `/post`. *Mitigation:* the "genuine failure still clears" test; the state must be
  **replaced**, not merely left dangling.
- *Risk:* two messages for the expired-draft condition (this block and phase 03 BLOCK 6).
  *Mitigation:* the re-read rule and the "one message per condition" rule.
- *Risk:* Q7 is never answered and a system error keeps being reported as a content verdict.
  *Mitigation:* the disposition must be **recorded** in the commit message even if the
  answer is "deferred".
- *Rollback:* the return-type change and the bot rewrite are **one commit**; reverting half
  leaves a type mismatch. Revert both or neither.

---

### BLOCK 13 — Seller-scoped photo dedup returns another ad's row (AD-006, Q6)

| | |
|---|---|
| **Findings owned** | `05-AD-006` |
| **`depends_on`** | **Q6 gate** — and must be sequenced against phase 07 `MEDIA-002` |
| **Priority** | P3 |
| **Roster** | **Implementor, Auditor, Planner, Validator** → *not* all five |

**This block is owner-gated (Q6). If phase 07 ships `MEDIA-002` first, this block becomes a
cross-reference and ships no code.**

**Agent requirement decision.**
- **Implementor — yes.** Always.
- **Auditor — yes.** Must confirm at the anchor that `create_or_skip` is still
  **seller-scoped**, and must produce the **caller inventory** — the code context records
  that `submit_ad` is the only production caller and **discards the return value**, which is
  the whole reason the bug is user-visible.
- **Researcher — no.** If Q6 has been answered in phase 07's favour, the fix shape is
  already specified by `MEDIA-002`. If it has been answered in phase 05's favour, the shape
  is the report's minimal re-scoping. There is no third question.
- **Planner — yes.** The block's design question is narrow but real: re-scoping the lookup
  to `(ad, sha256)` leaves the **staged file orphaned** on disk, because the file was
  already promoted by `move_staging_to_permanent` before the dedup ran. That is an FS
  consequence, and it is why this block is not a one-line change regardless of Q6.
- **Validator — yes.** The change alters when a file is created, and phase 07's `MEDIA-001`
  is a **hard dependency** of the file-lifecycle half. Getting it wrong orphans files or,
  worse, frees bytes another row references.

#### 3.13.1 Owner gate — Q6 (which record is `AD-006` and which is `MEDIA-002`?)

**Same behaviour, two records, two ratings, two remediation descriptions.** The code context
is explicit: *"An owner decision on which record survives is required — it is not derivable
from the code."*

| Record | Owner phase | Rating | Described fix | Rollout position |
|---|---|---|---|---|
| `MEDIA-002` | **Phase 07** | **HIGH** | *"Reclaim the skipped file"* — create a fresh row under a freshly generated unique key | **First** in phase 07's rollout: *"Landing it first removes the accidental-aliasing vector entirely, shrinking `MEDIA-001`'s problem from three producers to two intentional ones."* |
| `AD-006` | **Phase 05** | MEDIUM | Re-scope the dedup lookup to `(ad, sha256)` | — |

Phase 07's own cross-phase table states: **"`AD-006` (05) — same behaviour as `MEDIA-002`
from the ads side, rated MEDIUM there. `MEDIA-002` is the higher-rated record."**

| Answer | Phase-05 action |
|---|---|
| **`MEDIA-002` is the record** (the phase-07 reading) | **BLOCK 13 ships no production code.** It becomes: (i) a cross-reference in the plan, (ii) a check that phase 07's fix actually covers the ads-side call site, (iii) the record in BLOCK 14. **Shipping the minimal `AD-006` fix *alongside* `MEDIA-002` produces two patches for one predicate** — the exact hazard `VAL-004` was raised to prevent. |
| **`AD-006` is the record** (the phase-05 reading) | BLOCK 13 ships the ads-side fix and phase 07 must re-scope `MEDIA-002` to the media-side half. **The Planner must state which half is left**, because the two descriptions are not obviously the same patch. |

**The file-orphan consequence is the tie-breaker and belongs to whoever wins.** Today, a
duplicate is detected **after** `move_staging_to_permanent` has already moved the staged
file to permanent storage, and `submit_ad` then discards the returned row — so the promoted
file is on disk with **no** `AdImage` row pointing at it. It is reclaimed later by
`sweep_orphaned_media` (phase 03 BLOCK 8 / phase 07's scope). **Re-scoping the lookup alone
does not fix that**; it makes it the *normal* case rather than the rare one, because a seller
who posts the same photo to two ads is no longer unusual. **Whichever record wins must state
whether it addresses the orphan**, and if not, the orphan count grows. The Planner must
record this in whichever block ships.

**Findings and notes carried forward.**

1. **The mechanism is a mis-scoped filter.** `create_or_skip` filters
   `AdImage.objects.filter(sha256=sha256, ad__user_id=ad.user_id).first()` — scoped to the
   **seller**, not the **ad** — and returns that row, which may belong to a different ad. The
   second ad then has **0** `AdImage` rows and fails `_validate_image_count`
   (`min_images = 1`).
2. **The seller-facing message blames the wrong thing.** `submit_ad` reports
   *"Ad failed moderation. Please check your content and try again."* for what is an
   invisible photo problem. The code context notes this is "a message that points at their
   text, not at the invisible photo problem". **If the block changes the dedup, it should
   consider whether the message changes** — but that is a user-visible string with an i18n
   obligation, and it is a Q6-adjacent decision, not a free extra.
3. **The existing test stays green under a correct fix — and that is fine.**
   `test_ad_image_service.py::TestAdImageServiceCreateOrSkip::test_returns_existing_duplicate_same_user`
   calls `create_or_skip(ad_a, key)` **twice on the same ad** and asserts the same pk and
   `AdImage.objects.count() == 1`. Scoping to `(ad, sha256)` keeps it green. **The test has
   no cross-ad, same-seller case — that is the missing coverage and it is the direct
   regression guard this block must add.**
4. **Severity is contested in the other direction too.** The validator held the finding at
   MEDIUM (not the rubric's HIGH "photo count violated") because *"the trigger requires the
   seller to deliberately submit a byte-identical file to a second ad; the system does not
   violate the invariant on its own."* Phase 07 rates it HIGH. **The plan's disposition
   follows the record that wins Q6.**
5. **Only one production caller, and it ignores the return value.** `submit_ad`. The bot
   path (`ad_create/submit.py::process_preview` → `sync_to_async(submit_ad)`) and the web
   path both go through it. The web `ad_edit` branches pass `photos=[]`, so they never
   trigger it.
6. **This block must not touch the media layer.** `delete_adimage_files_on_delete`,
   `_collect_referenced_keys` and the storage-key ownership model are phase 07's
   (`MEDIA-001`), and the staging→permanent move is phase 03 BLOCK 8's decision (§5.2).

**File surface (semantic units).**
- `src/backend/apps/ads/services/images.py` → `AdImageService.create_or_skip` (the dedup
  filter and its docstring, which currently says *"Deduplication is scoped per seller"* — a
  docstring change is mandatory if the scope changes) and `AdImageService._compute_sha256`
  (read only).
- `src/backend/apps/ads/tests/test_ad_image_service.py` → `class TestAdImageServiceCreateOrSkip`
  (**add** the cross-ad same-seller case; **keep** the four existing cases unchanged).
- `src/backend/apps/ads/services/submission.py` → `submit_ad` (**read only**, unless the
  message changes per note 2).
- **Not touched:** `src/backend/apps/media/**` (phase 07), `sweep_orphaned_media.py`
  (phase 03 BLOCK 8 / phase 07).

**Tests required.**
- *Must be added:*
  - **The cross-ad, same-seller regression test:** the same bytes attached to `ad_a` and
    then to `ad_b` of the **same** seller ⇒ `ad_b` receives **its own** `AdImage` row and
    `create_or_skip` returns a row belonging to `ad_b`. Demonstrated **red** before the fix.
  - A test that a **different seller** posting the same bytes still creates a new row
    (unchanged behaviour — the guard against over-scoping the fix).
  - If the message changes: a test that the new message names the photo problem, and the
    i18n gate.
- *Must keep passing unchanged:* the four existing cases in
  `TestAdImageServiceCreateOrSkip`; `test_submission.py`; `test_copy_ad.py` in full.
- *Gate:*
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/ src/backend/apps/media/tests/" test`,
  then `.\Makefile.ps1 test`, then both static gates.

**Risk / rollback.**
- *Risk:* the block ships the minimal `AD-006` fix **after** phase 07 has shipped
  `MEDIA-002`, producing two patches for one predicate. *Mitigation:* the Q6 gate is a
  **hard** gate; the plan states the answer's consequence for each branch.
- *Risk:* re-scoping increases the orphan-file count without addressing it. *Mitigation:*
  the orphan consequence is a named part of whichever block wins.
- *Risk:* over-scoping the fix so that a *different seller*'s identical file is reused.
  *Mitigation:* the "different seller still creates a new row" test.
- *Rollback:* one commit, no migration. Clean revert.

---

### BLOCK 14 — Records: retired `AD-003`, reserved `AD-015`, the `VAL-005` answer, and the ID convention

| | |
|---|---|
| **Findings owned** | `05-AD-003` (retired), `05-AD-015` (reserved), `05-VAL-005`'s record, `05-VAL-006`'s record, the `05-VAL-001` sweep boundary |
| **`depends_on`** | Runs **last**, after every other block — it records their outcomes |
| **Priority** | P3 |
| **Roster** | **Implementor, Validator** |

**Agent requirement decision.**
- **Implementor — yes.** It writes code comments and this plan's own record sections.
- **Auditor / Researcher / Planner — no.** Nothing is uncertain; the decisions are made by
  this point and the block's job is to record them accurately. An extra analysis pass would
  add latency and could only re-litigate decisions that are already closed.
- **Validator — yes.** The block's whole risk is an *inaccurate record* — a retired finding
  written up as open, a reserved finding written up as fixed, or a cycle number **inferred**
  rather than evidenced. An independent read of the records against the block outcomes is
  the only control.

**This block is documentation-only and it must not grow into a sweep.** Its purpose is to
make sure the final report does not read as though four findings are open and unowned.

**Findings and notes carried forward.**

1. **`AD-003` is retired, and the record must say so in the finding's own words.** Phase 07
   ruled the invariant is **N references, refcount-aware free**; the `pre_delete` half is
   **absorbed into `MEDIA-001`**; `copy_ad` aliasing is **legal behaviour, not a bug**; and
   the data-loss half is **retired by `MEDIA-001`'s fix**. The residual is a *design
   trade-off with no defect in it*: *"a copy shares bytes with its source, which is cheap in
   disk and means the copy has no independent photo lifecycle."* `VAL-004` is **resolved**.
   **The block's one code deliverable** is updating
   `src/backend/apps/ads/services/copy_service.py`'s module docstring and the image-loop
   comment so the ads layer states the decided rule and the trade-off, rather than leaving
   the next reader to re-derive it. **It must not change `copy_ad`'s behaviour.**
2. **`AD-015` is a real defect with no phase-05 fix, and the record must say that
   explicitly.** `ads_auto_publish=False` does not hide a published ad:
   `ListingsQuery.build_queryset` filters `status=PUBLISHED, user__is_declined=False` with no
   `ads_auto_publish` term, while `can_publish_ad(user)` is `False` for such a user. The
   `UserAdmin` exposure half is **phase 04 BLOCK 1**; the queryset-level predicate is **phase
   06 `PII-104` + `VAL-003`** and **phase 15 `AUTHZ-005`**. **Recording it as "deferred to
   the owner of the predicate" is the correct outcome** — inventing an `is_ads_visible` here
   would create the second ad-hoc predicate phase 06's `VAL-003` exists to prevent.
3. **The `VAL-001` boundary must be stated, not enforced.** The plan-wide convention is
   **cycle-scoped IDs** (`05-ad-lifecycle-AD-00N` / `05-VAL-00N`). BLOCK 1 disambiguates the
   three bare IDs inside `Ad.transition_to`. **The repository-wide sweep of the ~68 legacy
   citations is phase 03 BLOCK 11's and is gated on a coordinator decision** — this block
   must **not** start it, must **not** extend BLOCK 1's rewrite to other files, and must
   record that the boundary was respected.
4. **`VAL-005` and `VAL-006` are recorded as decisions with their answers.** Whatever Q4
   and Q1 produced, the answer and its rationale belong here so the final report cites a
   decision rather than an open question.
5. **Never infer a cycle number.** Where a legacy citation's origin is uncertain, prefer the
   **descriptive form** (say what the code does) over a guessed attribution. An
   implementation that invents `AD-002 (phase 04)` is arguably worse than today's honest
   ambiguity. Phase 03 BLOCK 11's Option C is the shape.

**File surface (semantic units).**
- `src/backend/apps/ads/services/copy_service.py` → the module docstring and the image-loop
  comment in `copy_ad` (**comments only — no behaviour change**).
- This plan file: §2, §5 and the block records. **A Planner-owned file; no block other than
  this one updates it, and it is not committed as part of a code block.**

**Tests required.**
- **None, and this is deliberate.** The block changes no behaviour. A test asserting a
  docstring's content would be exactly the "trivial implementation detail" test this
  plan's contract forbids.
- *Must keep passing unchanged:* `test_copy_ad.py` in full — the docstring change must not
  alter `copy_ad` at all.

**Risk / rollback.**
- *Risk:* the docstring rewrite is read as a behaviour change and phase 07's
  `test_copy_ad_happy_path` reds. *Mitigation:* comments only; the diff is reviewed for
  that.
- *Risk:* the `VAL-001` record is read as "start the sweep". *Mitigation:* the boundary is
  stated in the commit message.
- *Rollback:* trivial — comments and a plan file. No code, no data.

---

## 4. Dependency graph

### 4.1 Execution order

```
BLOCK 1  AD-013 + AD-011  Hoist the matrix; clear archived_at on re-publish   deps: —
      │     ══► HARD edges: BLOCK 2 (needs a named matrix to add an edge to)
      │     ══► HARD edges: BLOCK 6, BLOCK 8 (the matrix is their edit surface)
      │     ══► SOFT: BLOCK 14 (it disambiguates three IDs in this function)
BLOCK 2  AD-009          Price/photo edit restarts the publish clock           deps: BLOCK 1  [Q3 gate]
      │     ──► SOFT: BLOCK 7 (same retention story; must not assume an anchor)
BLOCK 3  VAL-003         Restore the human approval path                       deps: —
      │     ══► HARD edge (VAL-003): BLOCK 6  — the single most important edge in the plan
BLOCK 4  VAL-002         Make the suite reach ON_MODERATION honestly           deps: —
      │     ══► HARD edge (VAL-002): BLOCK 5
BLOCK 5  AD-008          Make ON_MODERATION durable                            deps: BLOCK 4, BLOCK 3  [Q2 gate]
      │     ──► SOFT: BLOCK 6, BLOCK 12 (shared status semantics; same function)
BLOCK 6  AD-001          One sanctioned lifecycle write path in the admin      deps: BLOCK 1, BLOCK 3  [Q1, Q8 gates]
BLOCK 7  AD-004          Retention anchor + delete-sweep predicate + index    deps: BLOCK 2 (soft)  [Q4 gate]
      │     ══► HARD edge (migration number): BLOCK 10
BLOCK 8  AD-002          Editing a failed ad must not be a dead end            deps: BLOCK 1  [Q5 gate]
BLOCK 9  AD-010          Bulk moderation: transaction, lock, honest errors    deps: BLOCK 3 (soft)  [Q11 gate]
BLOCK 10 AD-014          AdImage.position uniqueness + migration              deps: BLOCK 7  [Q9 gate]
BLOCK 11 AD-012 (bot)    ad_copy: no raw driver error to the seller           deps: phase 03 BLOCK 10
BLOCK 12 AD-016          An expired draft is not a moderation failure         deps: BLOCK 5 (soft), phase 03 BLOCK 6  [Q12, Q7]
BLOCK 13 AD-006          Seller-scoped dedup returns another ad's row         deps: Q6 gate (phase 07 MEDIA-002 may pre-empt)
BLOCK 14 records         AD-003 retired, AD-015 reserved, VAL-005/006 answers  deps: all (runs last)
```

**Safe serial order:** `1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14`.

Exactly one Implementor runs at a time, so the order is always serial. The DAG records the
edges that **must not be inverted** — the ones where starting a block before another has
landed produces a worse system than leaving both undone.

### 4.2 Why each edge exists

| Edge | Kind | Reason |
|---|---|---|
| **3 → 6** | **HARD — `VAL-003`** | **The most important edge in the plan.** The obvious `AD-001` fix is `AdAdmin.status` → read-only. But `bulk_approve` returns 0, the approve view 404s, and `approve_ad` returns `False` for every real ad, so the four `action_*` buttons and the review view are the **only** sanctioned moderator write paths — and they cannot approve anything. Ship `status` → read-only first and **moderators lose the ability to publish entirely**. BLOCK 6's internal ordering (the read-only change lands last) is a second, independent guard. |
| **4 → 5** | **HARD — `VAL-002`** | Making `ON_MODERATION` durable without first fixing the suite leaves the ~fabricated tests **green against the newly real state**, so the suite reports success while having validated nothing. The fabrication channel is a fixture **default**, not an argument — the report's `34` cannot see it (§0.2.3). Reversing this order is the difference between a verified fix and an unverified one. |
| **1 → 2** | **HARD** | `AD-009`'s fix needs somewhere to put a `PUBLISHED → PUBLISHED` edge, and the matrix is a function-local literal. Without BLOCK 1 the only shape is Option B — a second writer of `published_at`, which is exactly the "three partial notions of last seller activity" `VAL-005` warns against. |
| **1 → 6** | **HARD** | `AD-001`'s sanctioned write path routes through `transition_to`, whose matrix must be a **named, importable** value for the service and the `ModelAdmin` override to reference it and for `Q8`'s previous-status logic to be testable. |
| **1 → 8** | **HARD** | `AD-002` option (b) **adds** an `ON_MODERATION_FAILED → ON_MODERATION` edge. Same requirement as `1 → 2`. |
| **7 → 10** | **HARD (migration number only)** | Both blocks generate the next `apps/ads` migration. `src/backend/apps/ads/migrations/` ends at `0007`, so `0008_*` is next — and **phase 03 BLOCK 6 also claims `0008_*`**. Two migrations with the same number in one app is a hard failure, not a merge conflict. Running BLOCK 7 first means BLOCK 10 takes `0009`; the reverse order is equally safe *provided* both re-read the directory immediately before generating. |
| **2 → 7** | **SOFT** | Both touch the retention story. BLOCK 2 resets the clock; BLOCK 7 decides what the clock measures and how long it runs. Reversing them is safe **provided** BLOCK 2 does not assume an anchor — its gate table says the reset is correct under *every* candidate anchor, and BLOCK 7 must not change the window. |
| **3 → 5** | **SOFT** | Under Q2 option (i) the newly durable `ON_MODERATION` rows are exactly what BLOCK 3's widened gates need to act on. Shipping BLOCK 5 first is safe but leaves the queue populated and unusable; shipping BLOCK 3 first is safe and immediately useful (for the `ON_MODERATION_FAILED` population). Ordering BLOCK 3 first is chosen, not required. |
| **3 → 9** | **SOFT** | The bulk endpoint and the review view are the same subsystem with the same status semantics. BLOCK 9 must know the approvable set BLOCK 3 established. No correctness dependency. |
| **5 → 6** | **SOFT** | If Q2 option (i) lands, `AdAdmin`'s sanctioned path has a *newly real* target status available, and BLOCK 6's `Q1` options are read differently. Not a correctness dependency — a **context** dependency, and BLOCK 6 must re-read rather than assume. |
| **5 → 12** | **SOFT** | `AD-012` and `AD-016` both live in `submit_ad`'s return contract. More importantly, Q7 (`_pass_moderation`'s bare handler converting a system error into a content verdict) becomes materially **worse** under Q2 option (i), because the failure would then cross a transaction boundary. **Q7 must be answered before option (i) ships**; BLOCK 12's Q7 disposition is recorded so the interaction is not lost. |
| **phase 03 BLOCK 10 → 11** | **HARD (cross-phase)** | `AD-012`'s DB half is `03-DB-009`, including the single-draft product rule. Phase 05's message must not be written for a condition whose rule is undecided. |
| **phase 03 BLOCK 6 → 12** | **HARD (cross-phase)** | `AD-016`'s sweep half and the seller-facing "your draft expired" **message** are `03-DB-003`. **One message per condition** — phase 05 reuses, never re-authors. |
| **Q6 → 13** | **HARD (gate)** | `AD-006` and `MEDIA-002` are one predicate with two records. If phase 07 ships first, BLOCK 13 ships **no code**. |

### 4.3 No edge exists for these, and why

- **BLOCK 3, BLOCK 4 and BLOCK 7 have no dependency on anything.** BLOCK 3 restores a dead
  control surface; BLOCK 4 is a test-fidelity change with no production dependency; BLOCK 7
  is gated on an owner decision, not on another block. All three could start on day one.
- **BLOCK 1 and BLOCK 2 do not depend on BLOCK 3, 4 or 5.** The state-machine foundation is
  independent of the moderation-path work — different files, different concerns. If the owner
  gates take a long time, `1 → 2` is a complete, useful, shippable unit of work.
- **BLOCK 9 does not depend on BLOCK 1.** It changes an HTTP endpoint's transaction
  boundary; the matrix is not involved.
- **BLOCK 10 does not depend on BLOCK 1 or BLOCK 2.** The only edge is the migration number.
- **BLOCK 11 does not depend on any phase-05 block.** It is one handler, one exception
  ladder, one message set. Its only edge is cross-phase.
- **BLOCK 14 depends on nothing and is listed last purely so it records settled outcomes.**
  It re-reads every file it touches, so ordering it last is strictly better for it.
- **BLOCK 8 does not depend on BLOCK 6**, even though `VAL-006` says the fix "should have
  exactly one place to live". That is a **design guidance**, not an ordering constraint: if
  BLOCK 6 lands first, BLOCK 8 writes the edge and the view branch into the sanctioned path;
  if BLOCK 8 lands first, BLOCK 6 adopts them. **Either order works; the commit message must
  say which.**

### 4.4 The gates that stop the DAG

**Five blocks are gated on an owner decision, and no agent in this plan can close any of
them.** They are not investigations.

| Gate | Blocks | Owner | Effect if the gate never closes |
|---|---|---|---|
| **Q1** — may a moderator move an ad's status, and through which seam? | **BLOCK 6** (fully) | **User / product, via the coordinator** | BLOCK 6's `status`-read-only half is not written. **The four unconditional fixes (no audit row, `original_published_at` mutability, owner transfer, the two 500s) plus the `search_vector*` removal still ship** — they are independent of Q1 and BLOCK 6's internal ordering puts them first. The block is therefore **degradable, not deadlock**. |
| **Q2** — which side of `ON_MODERATION` durability? | **BLOCK 5** (fully) | **User / product, via the coordinator** | BLOCK 5 does not start. BLOCK 3 still ships and is independently useful (it fixes the approve path for the `ON_MODERATION_FAILED` population). BLOCK 4 still ships and is *required* before any future BLOCK 5. The phase delivers a test suite that can actually validate `ON_MODERATION` and a working approve path — a strict improvement over the audit baseline, with `AD-008` recorded as open-and-gated. |
| **Q4** — the retention anchor | **BLOCK 7** (the anchor half) | **User / product, via the coordinator** | BLOCK 7 does not start. This is the one HIGH in the plan that cannot be partially delivered, because "correct" is undefined without the answer. It is recorded in BLOCK 14 as an open owner decision. |
| **Q5** — the failed-ad edit rule | **BLOCK 8** (fully) | **User / product, via the coordinator** | BLOCK 8 does not start. The structural half — replacing the `else:` catch-all with an explicit status allow-list — is arguably shippable without Q5 and would make the branch's behaviour defined for all seven statuses. **The Planner may propose that split; this plan does not decide it.** |
| **Q6** — `AD-006` vs `MEDIA-002` | **BLOCK 13** (fully) | **Coordinator** | BLOCK 13 ships no production code and becomes a cross-reference plus a record. **This is the intended de-scope path**, not a failure: phase 07's report already says `MEDIA-002` is the higher-rated record and orders it first in its own rollout. |

**Six blocks carry internal decision gates** (Q3, Q7, Q8, Q9, Q10, Q11, Q12). Those are
**Researcher/Planner** questions, closed inside the block before implementation starts, and
the chosen option is recorded in the block's commit message. §8.2 checks them.

**Q9 is the only one that is a data fact rather than a judgement**, and the only one whose
gate cannot be closed by reading code.

---

## 5. Cross-phase coordination

Phases 01 and 02 are executed or in flight. **Phases 03 and 04 have plans** (`.ai/plans/
03-db-concurrency-remediation.md`, `.ai/plans/04-auth-login-remediation.md`); **phases 06–15
are being planned in parallel right now.** This section is a boundary contract, deliberately
one-directional: **phase 05 states what it owns and what it will not touch. It does not
attempt to contact the other agents and does not assume their answers.**

### 5.1 What phase 05 already owns and must not re-ship

| Already owned elsewhere | Where it lives | What phase 05 must **not** do |
|---|---|---|
| **`AD-005` ≡ `03-DB-001`** (phase 03 BLOCK 4) | `src/telegram_bot/services/ad_data/orm.py` → `create_draft_ad`. Still open in the tree — the INSERT is wrapped in the outermost `atomic()` and the `except IntegrityError` branch's first statement queries an already-aborted transaction. | **Ship nothing.** The validator merged it; phase 03 rated the same defect MEDIUM and escalated the re-rating as `03-VAL-003`. **One work item, one commit, one severity.** If phase 05 needs `copy_ad` to honour the one-draft invariant, it adopts phase 03 BLOCK 10's decision (`03-DB-009`), not a fresh one. |
| **`AD-007` (sweep half) ≡ `03-DB-003`** (phase 03 BLOCK 6, HIGH) | `sweep_drafts.Command.handle`; `IX_ads_draft_sweep`; **and the seller-facing "your draft expired" message**. | Ship nothing for the sweep half. **And do not add a second "your draft expired" message** — phase 03 already owns that string (BLOCK 12's rule: one message per condition). |
| **`AD-012` (DB half) ≡ `03-DB-009`** (phase 03 BLOCK 10) | `copy_ad`'s single-`DRAFT`-invariant handling and its product rule. | Ship nothing for the DB half. BLOCK 11 is the **bot** half only, and it is sequenced **after** phase 03 BLOCK 10. |
| **`AD-003` (`pre_delete` half) ≡ `07-MEDIA-001`** (phase 07) | `apps/media/signals.py` → `delete_adimage_files_on_delete`; the storage-key ownership model. | **Do not add refcounting. Do not copy bytes. Do not change `delete_adimage_files_on_delete`.** Phase 07's `VAL-002` is explicit that doing "copy the bytes" alongside a refcount-aware `pre_delete` *"pays for both remediations and gains nothing."* |
| **`UserAdmin` field contract** (phase 04 BLOCK 1, `04-AUT-005` / `04-VAL-004` / merged `PII-103`) | `src/backend/apps/users/admin.py` → `UserAdmin`. Phase 04 requires `ads_auto_publish` (with `is_declined`, `is_deleted`) to be **removed from the form entirely**, not marked read-only. | Phase 05 must not edit `UserAdmin`. This is `AD-015`'s exposure half and it is **gone** once phase 04 lands. |
| **The account-state / visibility predicate** (phase 06 `PII-104` + `VAL-003`; phase 15 `AUTHZ-005`) | `apps/users/services/account_state.py` → `AccountState`; `apps/ads/services/listings_query.py` → the queryset predicate. | **Phase 05 must not add `is_ads_visible` to `AccountState` and must not add an `ads_auto_publish` term to `build_queryset`.** Phase 15's `AUTHZ-001(d)` **forbids** folding `user__is_declined=False` into the gate and keeps publish gating in `apps/users` and ad visibility in `apps/ads`. Phase 04's §4.3 item 3 forbids shipping `can_publish_ad` and a new verdict side by side. `AD-015` is therefore **recorded, not fixed** (BLOCK 14). |
| **Per-batch sweep commits** (phase 03 BLOCK 7, `03-DB-008`) | `delete_sweep.Command.handle` and `archive_sweep.Command.handle` are **the same functions BLOCK 7 edits**. | BLOCK 7 must **not** do phase 03's per-batch restructuring and must **not** change the advisory-lock acquisition shape. If phase 03 BLOCK 7 has landed, BLOCK 7 re-reads. |
| **The redundant `storage_keys` pre-collection** (phase 03 BLOCK 1, `03-DB-011`) | `delete_sweep.Command.handle` — the same file as BLOCK 7. | BLOCK 7 must not remove it. It is phase 03's, and the block that removes it may not have landed. |
| **`AdvisoryLockId` inventory** (phase 03 allocates **none**) | `src/backend/apps/core/enums.py`. Phase 03's plan records 18 members with ID 10 reserved. **The code context's addendum notes `REPAIR_BOT_USERNAME = 13` appeared during the audit pass, so phase 03's copy of that table is stale.** | **Phase 05 allocates no `AdvisoryLockId` member either.** No phase-05 block needs a new lock. If one is ever forced, `enums.py`, the allocation table in `advisory_lock.py`'s docstring, and `test_advisory_lock_ids.py` all change in one commit and the coordinator is told first. |
| **`record_event`'s transaction boundary** (phase 03 BLOCK 3, `03-DB-002`) | `apps/core/services/analytics.py`. BLOCK 5's option (i) changes the `atomic()` **nesting depth** around `auto_moderate`. | BLOCK 5 must **not** change `record_event`, and must re-read phase 03's BLOCK 3 reasoning if it has landed, because the nesting change interacts with it. |
| **The ad-detail query budget** (phase 03 BLOCK 3, §0.2.3 of its plan) | `apps/ads/tests/test_ad_detail_queries.py` → `_QUERY_BOUND = 16`. | No phase-05 block adds a query to the `AD_VIEWED` path, but **BLOCK 2 and BLOCK 6 must run that test** rather than assume it. |
| **The `ADMIN` role predicate** (phase 15 `AUTHZ-003` / `AUTHZ-005`) | `AdAdmin.has_change_permission` / `has_view_permission`; `AccountStateMiddleware` in the bot. | **BLOCK 6 must not change `AdAdmin`'s permission predicate** — it is phase 15's surface. Phase 15's validator did not re-file `AD-001` precisely because phase 04/05 owns the **field set**. |
| **The finding-ID namespace sweep** (phase 03 BLOCK 11, gated on a coordinator decision) | ~68 legacy citations across ~26 shipped files. | **Phase 05 must not start the sweep.** Its own scope is the three bare IDs inside `Ad.transition_to` (BLOCK 1) plus the plan-wide cycle-scoped convention. |

### 5.2 What phase 05 must **not** do, for other phases' sake

| Other phase | What phase 05 must not do | Boundary |
|---|---|---|
| **Phase 06** (`PII-104`, `VAL-003`, `PII-113`) | Must not add a queryset-level consent predicate, must not add `is_ads_visible`, and **must not edit `docs/01-spec/technical-specification.md`** — phase 06 `PII-113` is editing it, and decision J (the retention anchor) and decision A/Q (the moderation gate) live there. Any documentation the plan wants to change in that file is **routed to the coordinator** instead. | BLOCK 7's DOC-UPDATEs are `db-retention.md`, `db-indexes.md` and the two user-story files — **never** the technical specification. |
| **Phase 07** (`MEDIA-001`, `MEDIA-002`, `MEDIA-009`) | BLOCK 13 must not ship a `create_or_skip` scope change **alongside** `MEDIA-002`; BLOCK 14 must not add refcounting or change `delete_adimage_files_on_delete`; no block may change the storage-key ownership model. | `apps/media/**` is **read-only** for every phase-05 block. `copy_service.py`'s **comments** are BLOCK 14's only media-adjacent edit, and they change no behaviour. |
| **Phase 08** (search / FTS) | Must not touch the `search_vector*` columns, the `ads_search_vector_update` trigger, or the `setup_search_triggers` DDL. BLOCK 6 **removes four `search_vector*` fields from the admin form** — that is a *form* change, not a *column* or *trigger* change, and it is safe. | The trigger neutralises manual edits, so removing the form fields is a hygiene fix with no functional coupling. |
| **Phase 10** (code quality) | Phase 10 will read `Ad.transition_to` and `create_test_ad`. If it changes either, **phase 05 must re-read rather than assume** — specifically BLOCK 1's extraction and BLOCK 4's fixture default. | The code context names this explicitly. |
| **Phase 11** (test coverage) | The test rewrites in BLOCK 2, BLOCK 3, BLOCK 4, BLOCK 8 and BLOCK 12 are **incidental rewrites required by a behaviour change**, not coverage improvements. Phase 11 must not claim them, and phase 05 must not expand them into new coverage while rewriting them. | A rewrite that grows into new coverage raises the block's regression risk. |
| **Phase 12** (production ops) | Phase 05 introduces no alert on the moderation queue. **If phase 12's `OPS-003` lands first, phase 05 must carry its warning forward** — a naive `pending_moderation` alert is dead on arrival until BLOCK 5 makes the queue real, and would then fire on real numbers for the first time. | BLOCK 3 note 7 records this. |
| **Phase 14** (i18n) | BLOCKs 8, 11 and 12 add user-visible strings. `src/backend/locale/*/LC_MESSAGES/django.po` is **shared**. **Append only — never run a wholesale `makemessages`** that would discard a concurrent phase's additions. | §5.3. |
| **Phase 15** (`AUTHZ-001` … `AUTHZ-005`) | BLOCK 6 must not change `AdAdmin`'s permission predicate. No block may touch `AccountStateMiddleware` in the bot. | Phase 15 audits the *permission predicate*; phase 05 owns the *field set*. Phase 15 explicitly said AD-001 is "a different subsystem" from its own findings and did not re-file it. |

### 5.3 Shared-artefact reservations

| Artefact | Claimed by | Risk and rule |
|---|---|---|
| **`src/backend/conftest.py`** | **BLOCK 4** — the **one** justified exception in this plan | **The most contended file in the repository.** Phase 03's plan states phase 03 **must not edit it at all**; that is respected here — phase 05 edits it only because `VAL-002` is about its fixture default. The change must be **only** the `status` default; no other fixture, no other parameter, no formatting. `src/telegram_bot/tests/conftest.py` must change in the same commit. **Re-read immediately before editing; stage by explicit path.** |
| **`src/backend/apps/ads/migrations/` — the next number** | **BLOCK 7** (`0008_*` if free) and **BLOCK 10** (`0009_*` or later). **Phase 03 BLOCK 6 also claims `0008_*`** for `IX_ads_draft_sweep`. | **Three-way contention on one number.** Serialisation: phase 05 takes `0008` only if phase 03 has not already generated it; the directory is listed **immediately before generating**, every time. **The safe order is BLOCK 7 → BLOCK 10** so the two phase-05 migrations are monotonic. Two migrations with the same number in one app is a **hard failure**, not a merge conflict. If phase 05 takes `0008` first, **phase 03 must be told** (coordinator, not another agent). |
| **`src/backend/apps/core/management/commands/delete_sweep.py`** | **BLOCK 7** (predicate, cutoff, possibly a row lock). **Phase 03 BLOCK 1** (removes the `storage_keys` pre-collection) and **phase 03 BLOCK 7** (per-batch commits). | **Three claims, one function.** BLOCK 7 must not touch the key collection and must not restructure the transaction. If either phase-03 block has landed, BLOCK 7 re-reads the whole function. |
| **`archive_sweep.py`** | **Phase 03 BLOCK 7** (per-batch commits). Phase 05 **reads only**, to confirm the auto path is unaffected. | No phase-05 block writes to it. |
| **`src/backend/apps/ads/models.py`** | **BLOCK 1** (matrix hoist, `PUBLISHED` branch, three audit-ID comments, `Ad.Meta.indexes`), **BLOCK 2** (the new matrix edge), **BLOCK 7** (`IX_ads_delete_sweep`), **BLOCK 8** (option b: the `ON_MODERATION_FAILED` edge), **BLOCK 10** (`AdImage.Meta`). **Phase 03 BLOCK 6** (`IX_ads_draft_sweep`). | **The most contended production file in the plan.** Five phase-05 blocks touch it, plus phase 03. The serial order `1 → 2 → 7 → 8 → 10` keeps every edit monotonic, and **BLOCK 1 must land first** because BLOCKs 2, 7, 8 and 10 all build on its output. Each block re-reads before editing. |
| **`src/backend/apps/ads/views/edit.py`** | **BLOCK 2** (price branch), **BLOCK 8** (catch-all branch), **BLOCK 12** (the two `submit_ad` branches, read-mostly). **Phase 03 BLOCK 5** split this file into a bot-side and a web-side surface. | Three phase-05 blocks, one function (`ad_edit`) plus two others. BLOCK 2 and BLOCK 8 touch **different branches** of the same function, which is why they are separate blocks rather than one: the branch boundaries are a review boundary. BLOCK 12 mostly reads. |
| **`src/backend/apps/ads/services/submission.py`** (`submit_ad`) | **BLOCK 5** (the `ON_MODERATION` transition and the `auto_moderate` call), **BLOCK 12** (the `Ad.DoesNotExist` branch and the return contract), **BLOCK 13** (read only). **Phase 03 BLOCK 8** (the staging→permanent move), **phase 03 BLOCK 3** (the `record_event` call sites). | **The most contested service in the plan — five claims.** Serial order `5 → 12` is correct and BLOCK 12 must re-read BLOCK 5's result rather than assume (note 5 of BLOCK 12 states this explicitly: if BLOCK 5 option (i) landed, `test_submit_ad_rolls_back_when_auto_moderate_raises` has already been renamed by BLOCK 5). |
| **`src/backend/apps/moderation/admin_actions.py`** | **BLOCK 3** (`bulk_approve`'s filter, `approve_ad`'s guard). **BLOCK 9** (read only). **Phase 03** (lock behaviour). **Phase 04 BLOCK 9** (comments only). | Phase 05 changes the **filter**, not the locking. `TestBulkLockingStructure`'s source-inspection guard and phase 04's `test_bulk_ban_users_not_locked` both constrain the shape and must stay green. |
| **`src/backend/apps/ads/admin.py`** (`class AdAdmin`) | **BLOCK 6** exclusively. **Phase 15** cites it (`AUTHZ-003`) and **phase 07** re-confirmed its field set. | **Phase 05 owns the field set; phase 15 owns the permission predicate.** One block, one owner. |
| **`copy_service.py`** (`copy_ad`) | **BLOCK 14** (docstring comments only). **Phase 03 BLOCK 10** (the single-draft policy). **Phase 07** (the storage-key model, now decided). | **Phase 05 ships no behaviour change to `copy_ad`.** The comments must not read as a behaviour change, and `test_copy_ad_happy_path` must stay green. |
| **`src/backend/apps/media/**`** | **Phase 07** (`MEDIA-001` and the whole ownership model). **Phase 03 BLOCK 8** (the promotion move). | **Read-only for every phase-05 block.** BLOCK 13 does not change `create_or_skip`'s file handling; it changes the *query scope*. |
| **`src/backend/apps/users/services/account_state.py`**, **`listings_query.py`**, **`users/admin.py`** | **Phase 15 `AUTHZ-005`**, **phase 06 `PII-104` + `VAL-003`**, **phase 04 BLOCK 1**. | **Read-only for phase 05.** `AD-015` is recorded, not fixed (BLOCK 14). |
| **`src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po`** | **BLOCK 8, BLOCK 11, BLOCK 12** (and phase 14) | **Append only.** Never regenerate wholesale. `ru` **and** `bs` `msgstr` must both be non-empty; `en` may be empty. |
| **`AdvisoryLockId`** | **Nobody in phase 05.** | No phase-05 block allocates a member. See §5.1. |
| **`docs/01-spec/technical-specification.md`** | **Phase 06 `PII-113`.** | **No phase-05 block may edit it.** Decisions A, J and Q live there, so BLOCK 7's documentation reconciliation routes to the user-story and database files instead. |
| **`.ai/audit/**`** | **Nobody. Unmodifiable by mandate.** | 19 tracked deletions exist. `git status --short .ai` must show no *new* modifications. |
| **`.ai/plans/**`** | Each Planner owns its own file. | This plan may not edit `01-…` … `04-…`. |

### 5.4 The `AD-015` split — stated once, so it is not re-derived

`AD-015` is a **real behaviour defect** with **no phase-05 fix**, and the record must say so
plainly so the final report does not read as an open unowned finding.

| Half | Owner | Phase-05 action |
|---|---|---|
| `ads_auto_publish` (with `is_declined`, `is_deleted`) is editable on `UserAdmin`'s auto-built form — `UserAdmin` declares no `fields`, no `fieldsets`, no `form` | **Phase 04 BLOCK 1** | **None.** Phase 04 removes them from the form entirely. |
| A single queryset-level account-state / visibility predicate | **Phase 06 `PII-104` + `VAL-003`**; **phase 15 `AUTHZ-005`** | **None.** Phase 05 must not add `is_ads_visible` to `AccountState` and must not add an `ads_auto_publish` term to `ListingsQuery.build_queryset` — that would create the **second** ad-hoc predicate those findings exist to prevent. |
| The behaviour defect itself (`ads_auto_publish=False` does not hide a published ad) | **unowned** | **Recorded in BLOCK 14** with a pointer to both owners, so the coordinator can route it. |

### 5.5 The `AD-006` / `MEDIA-002` contention — stated once, for the coordinator

**This is the sharpest ownership conflict in the phase and it is not resolvable from the
code.** `AD-006` (phase 05, MEDIUM) and `MEDIA-002` (phase 07, **HIGH**) are **one
predicate** — `AdImageService.create_or_skip`'s seller-scoped dedup — with two records and
two remediation descriptions that are **not obviously the same patch**:

- `AD-006`'s minimal fix: re-scope the lookup to `(ad, sha256)`.
- `MEDIA-002`'s described fix: **reclaim the skipped file** — create a fresh row under a
  freshly generated unique key.

Phase 07's own cross-phase table states *"`MEDIA-002` is the higher-rated record"* and orders
it **first** in its rollout, on the grounds that landing it first *"removes the
accidental-aliasing vector entirely, shrinking `MEDIA-001`'s problem from three producers to
two intentional ones."*

**What phase 05 does:** asks (Q6) and waits. If phase 07 ships `MEDIA-002` first, BLOCK 13
ships **no production code** and becomes a cross-reference. **Phase 05 must not ship the
minimal `AD-006` fix alongside it** — two patches for one predicate is the exact hazard
`VAL-004` was raised to prevent.

**The tie-breaker the owner should know about:** re-scoping the lookup alone does **not**
address the orphaned promoted file (today a duplicate is detected *after*
`move_staging_to_permanent` has already moved the file, and `submit_ad` discards the
returned row). Whoever's record wins must state whether the orphan is addressed; if it is
not, the orphan count grows, because "a seller posts the same photo to two ads" stops being
a rare event.

### 5.6 The `AD-003` / `MEDIA-001` boundary — closed

Phase 07's validated report has **answered** the question phase 05 asked it (this phase's
`VAL-004`):

> **How many `AdImage` rows may reference one storage key? Answer: N, N ≥ 1.** The invariant
> is *"a key is freed only when its last referencing row goes away."* A refcount is the
> correct model. The chosen fix is a **reference check inside the existing `on_commit`
> callback** — no schema change, no migration, no new model.

Therefore: the `pre_delete` half is **absorbed into `MEDIA-001`**; `copy_ad`'s key reuse is
**legal behaviour, not a bug**; the data-loss half of `AD-003` is **retired by `MEDIA-001`'s
fix**; and **`AD-003` is RETIRED.** `VAL-004` is **RESOLVED**.

**Phase 05's residue** is a documentation deliverable in BLOCK 14: state the decided rule
and the trade-off in `copy_service.py`'s docstring, so the ads layer's statement matches
phase 07's media-layer statement (which phase 07 owns as `MEDIA-009`).

**The one thing phase 05 must not do, ever:** implement the byte-copy branch. If a future
reader of this plan believes the "copy the bytes" fix is available, they will re-open a
closed question and ship a second remediation for a defect that no longer exists.

---

## 6. Out of scope for this plan

| Item | Reason |
|---|---|
| **`AD-003` — the byte-copy fix** | **Forbidden by phase 07's ruling.** The `pre_delete` half is absorbed into `07-MEDIA-001`; `copy_ad` aliasing is legal under the refcount model; `VAL-004` is resolved. Shipping "copy the bytes" alongside a refcount-aware `pre_delete` pays for both remediations and gains nothing. BLOCK 14 records the trade-off. |
| **`AD-005` — `create_draft_ad`'s race backstop** | Phase 03 BLOCK 4 (`03-DB-001`) owns it. **Still open in the tree**, for the record; phase 05 ships no second patch. Phase 03 escalated the re-rating as `03-VAL-003`; phase 05 does not re-rate it. |
| **`AD-007` — the draft sweep predicate** | Phase 03 BLOCK 6 (`03-DB-003`, HIGH) owns the whole finding **including the seller-facing message and the `ads/0008_*` migration**. |
| **`AD-012`'s DB half — the single-`DRAFT` invariant** | Phase 03 BLOCK 10 (`03-DB-009`) owns it, including the product rule. BLOCK 11 is the bot half only and is sequenced after it. |
| **`AD-015` — the `UserAdmin` exposure** | Phase 04 BLOCK 1. It must be **removed from the form entirely**, not marked read-only. |
| **`AD-015` — the visibility predicate** | Phase 06 `PII-104` + `VAL-003` and phase 15 `AUTHZ-005`. Phase 05 must not add `is_ads_visible` to `AccountState` nor an `ads_auto_publish` term to `ListingsQuery.build_queryset`. See §5.4. |
| **`AdAdmin.has_change_permission` / `has_view_permission`** | Phase 15 `AUTHZ-003` / `AUTHZ-005`. Phase 15's validator explicitly did not re-file `AD-001` because phase 05 owns the **field set** and phase 15 owns the **permission predicate**. |
| **`AccountStateMiddleware` in the bot** | Phase 15. No phase-05 block touches it. |
| **The moderation queue's consumer surfaces** (the queue view, the priority service, `get_pending_queue_size`, the analytics dashboard, the `moderation_queues` admin preset) | They were written for a state that did not exist and become correct the moment BLOCK 5 makes it real. BLOCK 5 **reads and confirms** each one; it does not redesign them. |
| **The ~68 legacy audit-ID citations across the repository** | Phase 03 BLOCK 11, gated on a coordinator decision. Phase 05's `VAL-001` scope is the three bare IDs inside `Ad.transition_to` (BLOCK 1) plus the plan-wide convention. |
| **`record_event`'s transaction boundary** | Phase 03 BLOCK 3 (`03-DB-002`). BLOCK 5 changes the surrounding `atomic()` nesting and must **re-read** phase 03's reasoning rather than re-implement it. |
| **Per-batch sweep commits and the lock-held-once shape** | Phase 03 BLOCK 7 (`03-DB-008`). BLOCK 7 touches `delete_sweep.Command.handle` for the predicate only. |
| **The redundant `storage_keys` pre-collection in six sweeps** | Phase 03 BLOCK 1 (`03-DB-011`). BLOCK 7 must not touch it. |
| **The staging→permanent media move and its rollback window** | Phase 03 BLOCK 8 (`03-DB-005`), with a hard dependency on phase 07. |
| **The storage-key ownership model, `_collect_referenced_keys`, `delete_adimage_files_on_delete`** | Phase 07 (`MEDIA-001`, `MEDIA-009`). Read-only for phase 05. |
| **The `search_vector*` columns, the `ads_search_vector_update` trigger, and the `setup_search_triggers` DDL** | The DDL is created by a management command, not a migration — the source report flagged it and correctly deferred it to the database/operations phases. Phase 08 owns the columns. BLOCK 6 removes four **form** fields, which is unrelated. |
| **A new `AdvisoryLockId` member** | No phase-05 block needs one. If one is ever forced, `enums.py`, the allocation table in `advisory_lock.py`'s docstring, and `test_advisory_lock_ids.py` change in one commit and the coordinator is told first. |
| **Rewriting the state machine's semantics** | The state machine is small, correct and well covered. `AD-013` **extracts** the matrix; it does not redesign the transition rules. Where an edge is genuinely needed (`AD-009`, `AD-002` option b) it is added deliberately, inside a block, with the consequences recorded. |
| **Making retention windows environment-configurable** | Directly contradicts `docs/02-database/db-retention.md`: *"All retention values are hardcoded… No environment variables or CLI arguments (beyond `--dry-run`) are read for retention durations."* BLOCK 7 changes the **predicate and the anchor**, never the configurability. |
| **A reverse `CheckConstraint` (`status <> ARCHIVED ⇒ archived_at IS NULL`)** | The source report lists it as an advisory recommendation. It is a **schema** change, it would reject data written by the *unfixed* admin form, and its value depends on BLOCK 6's outcome. **Deferred** — if shipped, it must land **after** BLOCK 6, and it is recorded here so it is a decision rather than an omission. |
| **A migration on `apps/media` or `apps/core`** | Phase 05 needs **no** migration outside `apps/ads`. Do not create one to dodge a number collision. |
| **Any new dependency** | Nothing here needs one. Adding one requires `uv add`, a lockfile update and a CI `uv lock --check` pass. |
| **A moderation-queue alert** | Phase 12. If phase 12's `OPS-003` lands first, this plan **carries the warning forward** — the queue is structurally zero until BLOCK 5 lands, so a naive `pending_moderation` alert is dead on arrival and would then fire on real numbers for the first time. |
| **i18n framework changes, `makemessages` regeneration, locale-file rewrites** | BLOCKs 8, 11 and 12 **append** strings. A wholesale regeneration would discard a concurrent phase-14 edit (§5.3). |
| **Consolidating the four `_run_in_subprocess` test helpers; the 19 uncommitted `.ai/audit/**` deletions; the deleted `.ai/audit/05-ad-lifecycle/findings.md`** | Not this plan's to resolve. Recorded so no block's `git status` check mistakes them for its own work. |
| **Q7 — `auto_moderate`'s bare `except Exception` in `_pass_moderation`** | **Not this plan's finding.** The source report does not contain it; the code context raises it. BLOCK 12 records the disposition (fold in / file to phase 03 / defer) and the block ships either way. **But it must be answered before BLOCK 5 option (i) ships** — see BLOCK 5 note 4. |

---

## 7. Per-block risk register

Severity here is **this Planner's assessment of execution risk for the change**, not the
finding's severity. "Migration" covers DDL, backfill and rollback; "Lock ordering" covers
advisory-lock and row-lock acquisition; "Transaction boundary" covers `atomic()` nesting and
savepoint depth; "Data migration" covers existing rows whose meaning changes; "Compatibility"
covers whether a change breaks a shipped, intended behaviour.

| Block | Risk | Kind | Likelihood | Impact | Mitigation / detection | Residual |
|---|---|---|---|---|---|---|
| **All** | An implementor runs `git add -A` and commits the 19 `.ai/audit/**` deletions or another phase's uncommitted work | Process | Med | **High** | §1's hard staging rule; `git status --short` immediately before **every** commit; the audit tree is unmodifiable by mandate; §5.3 names the contended files. | Very low |
| **All** | A block starts before its `depends_on` has landed, or two Implementors run at once | Process | Low | **High** | §4.1 serial order; one Implementor, strictly sequential. `3 → 6` and `4 → 5` are the edges that matter. | Very low |
| **All** | A block's tests are **asserted** rather than **run**, or run on the host where there is no database | Process | Med | **High** | Every block names its exact Docker gate; tests run **only** through the `test` service (§1). | Low |
| **All** | A gate's decision (Q1–Q12) is closed silently by the Implementor instead of by the Researcher/Planner or the owner | Process | Med | **High** | Every gated block states its gate in the task `extra_context` and requires the decision in the commit message. §8.2 checks it. | Low |
| **All** | A new user-visible string ships without non-empty `ru` **and** `bs` translations | i18n | Med | Med | Only BLOCKs 8, 11 and 12 add strings; each names the locale files; §5.3 forbids a wholesale regeneration. | Low |
| **All** | A **shipped green test** that encodes a defect is "fixed" by changing production code instead | Correctness | Med | **High** | Project rule 2 restated in §1. Two tests are explicitly slated for rewrite (BLOCK 2, BLOCK 8) plus BLOCK 3's `test_approve_non_moderation_ad_returns_404` and BLOCK 4's retargeting. **Each block names the test and the justification.** §8.3 checks them. | Low |
| **All** | The `create_test_ad` default is changed in only **one** conftest | Correctness | Med | Med | BLOCK 4's hard requirement: the bot package redefines the fixtures. §8.3 checks both. | Low |
| **All** | A block edits a file another phase is editing right now and clobbers the change | Process | **Med** | Med | §5.3 names the contended artefacts; re-read immediately before editing; stage explicit paths. | Low |
| **1** | The `archived_at = None` assignment lands without the matching `update_fields` append — a **silent no-op** that still looks correct in review | Correctness | Med | Med | The mandatory test asserts on a **reloaded** instance, not the in-memory object. | Very low |
| **1** | The extracted matrix is not verbatim, so one edge silently changes | Correctness | Low | **High** | The matrix-identity test; `TestTransitionValidation` and `TestTransitionMatrixEdges` must pass untouched. | Very low |
| **1** | The audit-ID comment rewrite is extended to other files, colliding with phase 03 BLOCK 11 | Process | Low | Med | The file surface is bounded to one function; §5.1 states the boundary. | Very low |
| **2** | Option A's self-edge is later read as "a transition happened" and a consumer double-counts | Correctness | Med | Med | The commit message names the constraint; the "no `ModeratorActionLog` row" test; the `update_fields` list is specified. | Low |
| **2** | The clock reset causes a live listing to be auto-archived unexpectedly, and an operator reports it as a regression | Compatibility | **Med** | Med | This is the **intended** behaviour under every candidate anchor; the commit message must say so. | Low |
| **2** | `test_edit_published_price_only_stays_published` is "fixed" by editing production code back to the old behaviour | Correctness | Med | Med | Project rule 2; the test is named with its reason; it must be demonstrated **red** first. | Low |
| **3** | A gate is missed, the path is still dead, the block ships "restored", and BLOCK 6 then removes the raw form path — **moderators can no longer publish at all** | Correctness | Med | **High** | The hard `3 → 6` edge; the end-to-end non-zero-count and 2xx tests are **mandatory** and must be demonstrated red first; BLOCK 6's internal ordering puts the read-only change last. | Low |
| **3** | The widened gate hands `approve_ad` an ad whose transition the matrix refuses (`ON_MODERATION_FAILED → PUBLISHED`), producing a swallowed no-op or a 500 | Correctness | **Med** | **High** | Note 2 of the block makes this the block's hardest design question; the refused-transition test is mandatory. | Low |
| **3** | Retargeting `test_approve_transitions_to_published` etc. onto `ON_MODERATION` "because that is what they used" leaves them fabricating a state the system still cannot produce | Testing | Med | Med | The retargeting rule in BLOCK 4's taxonomy; **category (b) producer tests** must be retargeted, not merely re-asserted. | Low |
| **4** | The default-change commit lands alone and leaves the repository red | Process | Med | Med | The mandatory internal order; §8.2 requires green before the block closes. | Low |
| **4** | Over-rewriting — a mechanical sweep "fixes" category (a) consumer tests that were fine, inflating the diff across a dozen files | Scope | **Med** | Med | The triage rule is explicit; a consumer test that needs editing to survive the default change is **mis-classified** and the classification is revisited first. | Low |
| **4** | The census is narrower than reality (both published counts are floors taken at earlier anchors, and commits have landed since), so a fabrication channel survives | Testing | **Med** | **High** | The Auditor re-measures; the block records the number it actually found; §8.3 requires that BLOCK 5's green state came **after** a red baseline. | Med — accepted |
| **5** | An ad is committed as `ON_MODERATION` and the moderating step never runs: invisible to the seller, invisible to any consumer that filters the status out, reaped by nothing | **Data integrity** | Med | **High** | The recovery mechanism is **part of** option (i), not an afterthought; the recovery test is mandatory. | Med — accepted |
| **5** | `max_ads_per_user` is bypassed by concurrent pending ads publishing together | Business invariant | Med | Med | Note 7's design requirement and its test. | Low |
| **5** | `_pass_moderation`'s bare handler converts a system error into a content verdict **across a transaction boundary** (worse than today) | Correctness | Med | Med | **Q7 must be answered before option (i) ships** (BLOCK 5 note 4); the disposition is recorded in BLOCK 12. | Med — accepted |
| **5** | Rollback leaves real ads committed in `ON_MODERATION` with nothing moderating them | **Data integrity** | Low | **High** | The block must write the one-off re-drive-or-fail query into its task **before** shipping. | Low |
| **6** | `status` → read-only lands before BLOCK 3 and moderators lose the ability to publish entirely | **Availability** | Low | **High** | The hard `3 → 6` edge **and** the block's internal ordering (read-only last). Two independent guards. | Very low |
| **6** | A save routed through `transition_to` silently discards the form's other field values, because the method starts with `refresh_from_db()` | Correctness | Med | Med | Note 5; the change-form tests assert the **whole** saved row. | Low |
| **6** | A double `ModeratorActionLog` row or a double `AnalyticsEvent` under option (b) | Correctness | Med | Med | The "exactly one" assertions. | Low |
| **6** | The block changes `AdAdmin`'s permission predicate "while in there" and collides with phase 15 | Scope | Low | **High** | Explicitly forbidden in note 4 and §5.1. | Very low |
| **7** | The chosen anchor hard-deletes a seller's archived ad earlier than the user stories promise — **irreversible** | **Data loss** | Med | **High** | The owner's explicit answer; the auto-path test; the commit message records the answer. | Med — accepted |
| **7** | The new partial index is omitted and the sweep degrades to a sequential scan on the hottest table | Performance | Low | Med | The migration is a named deliverable; the index choice is a gate (3.7.2), not a nicety. | Low |
| **7** | **`0008_*` collides with phase 03 BLOCK 6** | Process | **Med** | Med | Re-read the directory immediately before generating (§5.3); the `7 → 10` ordering edge keeps phase 05's own two migrations monotonic. | Low |
| **7** | The migration's `ACCESS EXCLUSIVE` lock on `ads` stalls the bot | Availability | Low | Med | The DDL is index-only, not a table rewrite; 3.7.2's `CONCURRENTLY` question must be answered. | Low |
| **8** | Option (a) or (c) ships and the ad is still purged, only now with a message | Correctness | Med | Med | The gate table states plainly that (a)/(c) hide rather than fix; the commit message must record the accepted consequence. | Med — accepted |
| **8** | Option (b) lets a seller retry forever, resetting the 7-day purge timer on each attempt | Abuse | Med | Med | The retry bounding is **part of** the option and has its own test. | Low |
| **8** | The `else:` catch-all is left in place with one more `if` added — the exact thing the validator forbade | Correctness | Med | Med | The five-status enumeration test fails on any re-broadening. | Low |
| **9** | Option A makes every bulk moderation call all-or-nothing while the response still reports "completed 97 of 100" | Correctness | Med | Med | The mixed-batch test **distinguishes A from B** and must be demonstrated red for A. | Low |
| **9** | The error string is made "actionable" by interpolating the exception — the `AD-012` defect, one layer up | Data exposure | Low | Med | The "no raw driver text" assertion. | Very low |
| **9** | A lock is added to the bulk-**ban** path and reds phase 04's tripwire | Process | Low | Med | Note 5; `bulk_ban_users` is read-only in this block. | Very low |
| **10** | `AddConstraint` fails on real data because the pre-flight was run against the test database | Migration | Low | **High** | The pre-flight is a **hard gate** against production-shaped data; the query and its result go in the commit message. A green `test-recreate` is **not** evidence. | Low |
| **10** | A contiguity constraint is added "while in there" and breaks the shipped `[0, 2, 5]` positions test | Compatibility | Low | Med | The test is named as the guard; the model comment records that gaps are permitted. | Very low |
| **10** | The data migration's rollback does not restore the original positions | Migration | Low | Med | The block states the lossy direction before shipping. | Very low |
| **11** | "Fixing" the message by moving the exception to a log-only path and returning a generic string loses the seller's ability to act | Correctness | Med | Med | The per-condition tests; the log-detail test. | Very low |
| **11** | Two messages for the draft-exists condition, because phase 03 BLOCK 10's string lands after this block | Process | Med | Low | The hard cross-phase ordering; "one message per condition". | Low |
| **11** | The `.po` files are regenerated wholesale and a concurrent phase's additions are discarded | Process | Low | Med | **Append only** (§5.3). | Very low |
| **12** | The return-type change breaks a caller the inventory missed — a `TypeError` in production | Correctness | Med | Med | The mandatory caller inventory; the type is introduced and consumed in **one** commit, never half-way. | Low |
| **12** | The state is no longer cleared and a stale FSM context lingers into the next `/post` | Correctness | Med | Med | The "genuine failure still clears" test; the state must be **replaced**, not left dangling. | Low |
| **12** | Q7 is never answered and a system error keeps being reported as a content verdict | Correctness | Med | Med | The disposition must be **recorded** in the commit message even if the answer is "deferred". | Med — accepted |
| **13** | The block ships the minimal `AD-006` fix **after** phase 07 has shipped `MEDIA-002`, producing two patches for one predicate | Process | Med | Med | Q6 is a **hard** gate; §5.5 states each answer's consequence. | Low |
| **13** | Re-scoping increases the orphan-file count without addressing it | Storage | Med | Med | The orphan consequence is a named part of whichever record wins (§5.5). | Low |
| **13** | Over-scoping so a *different seller's* identical file is reused | Data | Low | Med | The "different seller still creates a new row" test. | Very low |
| **14** | The `copy_service.py` docstring change is read as a behaviour change and phase 07's test reds | Process | Low | Med | Comments only; the diff is reviewed for that. | Very low |
| **14** | A cycle number is **inferred** rather than evidenced, producing a confident-but-wrong attribution | Documentation | Med | Med | Note 5: prefer the descriptive form wherever attribution is uncertain. **Never infer.** | Low |
| **14** | The block is treated as cosmetic and de-scoped, leaving `AD-003` and `AD-015` reading as open and unowned in the final report | Process | Med | Med | It is the only block that makes four findings legible to the coordinator. Cheap; do not drop it. | Low |

---

## 8. Definition of done for the whole plan

Phase 05 is complete when **all** of the following hold. Checkboxes for blocks that are
**gated on an owner decision** are marked *(if the block shipped)* — the plan is still
"done" when the gate is recorded and the block is either shipped or explicitly recorded as
open-and-gated.

### 8.1 Scope

- [ ] All 16 `05-AD-*` findings have a recorded disposition: **12 implemented**
      (`AD-001`, `-002`, `-004`, `-006` *(if Q6 favours phase 05)*, `-008`, `-009`, `-010`,
      `-011`, `-012` *bot half*, `-013`, `-014`, `-016`), **2 partial** (`AD-012` DB half →
      `03-DB-009`; `AD-016` sweep half → `03-DB-003`), **2 superseded** (`AD-005` → `03-DB-001`;
      `AD-007` → `03-DB-003`), **1 retired** (`AD-003`, by phase 07's ruling), **1 reserved**
      (`AD-015`, to phases 04/06/15). **0 rejected.**
- [ ] All 6 `05-VAL-*` findings have a recorded disposition: `VAL-001` convention **decided**
      + BLOCK 1's disambiguation shipped + sweep **de-scoped to phase 03**; `VAL-002` shipped
      as BLOCK 4 and the `4 → 5` edge honoured; `VAL-003` shipped as BLOCK 3 and the
      `3 → 6` edge honoured; `VAL-004` **resolved** by phase 07; `VAL-005`'s decision (Q4)
      recorded; `VAL-006`'s decision (Q1) recorded.
- [ ] Every gated block (**2, 5, 6, 7, 8, 10, 12, 13**) has a **written** decision naming
      the option chosen and the consequences accepted — or, for the owner gates, a record
      that the gate is open and the block is deferred. **Silence is not an acceptable
      outcome.**
- [ ] Q1, Q2, Q4, Q5 and Q6 each have a recorded answer **or** a recorded "open — block
      deferred", with the consequences from §4.4 written down. **No owner decision was made
      by an agent.**
- [ ] The `AD-003` retirement and the `AD-015` reservation are recorded in BLOCK 14 so the
      final report does not present either as an open, unowned defect.
- [ ] `AD-005`'s HIGH-vs-MEDIUM re-rating (phase 03's `03-VAL-003`) is acknowledged, and
      **no second patch for `create_draft_ad` exists in this plan's history**.

### 8.2 Gates — all green

- [ ] `uv run ruff check src/` → exit 0.
- [ ] `uv run basedpyright src/` → **0 errors**. (The report's "12 errors in 2 files" is
      **superseded** and must not appear in any commit message or block.)
- [ ] `.\Makefile.ps1 test` → full fast suite green (`PYTEST_SKIP_MARKERS=seed`).
- [ ] `.\Makefile.ps1 test-recreate` executed at least **once after BLOCK 7's migration**
      and at least **once after BLOCK 10's migration**.
- [ ] Every block's **exact** gate command from §3 was run and green — not the full suite
      alone.
- [ ] `git status --short .ai` shows **no new modifications** beyond the pre-existing
      `.ai/audit/**` deletions. No audit-phase file was edited, restored or re-created.
- [ ] No `git reset`, `git checkout`, `git stash`, `git clean`, `git add -A` or
      `git add .` was run at any point. No commit was made without an explicit user request.
- [ ] Migration numbers were checked against `src/backend/apps/ads/migrations/`
      **immediately before each generation**, and the `0008_*` contention with phase 03
      BLOCK 6 was resolved and recorded.
- [ ] No block shipped a `AdvisoryLockId` member, a `config/settings/**` change, a new
      dependency, or a migration outside `apps/ads`.

### 8.3 Per-finding behavioural confirmation

- [ ] **`AD-001`** — an admin POST of a status change either is refused, or commits **with**
      exactly one `ModeratorActionLog` row and one `AnalyticsEvent` (per Q1).
      `original_published_at` is immutable through the form. `user` is not reassignable.
      A POST selecting `REJECTED` and one selecting `ON_MODERATION_FAILED` return a
      **validation error, not an HTTP 500**. `DELETED → published` through the form is
      refused. The four `search_vector*` fields are not in the form. Each new test was
      demonstrated **red** against the pre-fix code.
- [ ] **`AD-002`** — a POST to an ad outside the allow-list is refused with an actionable
      message and the ad is unchanged, **or** (option b) editing a failed ad re-moderates it,
      resets `moderation_failed_at` and survives `purge_failed_ads`. The five-status
      enumeration test exists. The dashboard Edit link is gated.
- [ ] **`AD-004`** — a manual archive back-dated 61 days is selected or not **per the chosen
      anchor**; the auto path still fires at `published_at + 120 d`; a long-lived archived ad
      is still eventually deleted; `delete_sweep --dry-run` writes nothing. The new partial
      index exists and `IX_ads_delete_sweep` is either removed or documented as retained.
      `db-retention.md` matches the shipped behaviour **including the duplicated fragment fix**.
- [ ] **`AD-006`** *(if shipped)* — the same bytes on two ads of one seller give the second
      ad its **own** `AdImage` row; a different seller's identical file still creates a new
      row. Demonstrated red first.
- [ ] **`AD-008`** *(if Q2 option i)* — an ad is durably `ON_MODERATION` between the two
      transactions, observed from a **separate connection**; it is absent from
      `ListingsQuery.build_queryset`; `get_pending_queue_size()` returns the real number; a
      crash in the moderating step leaves the ad recoverable; the `max_ads_per_user`
      interaction is bounded and tested.
- [ ] **`AD-009`** — a price-only and a photo-only edit of a `PUBLISHED` ad leave the status
      `PUBLISHED` and move `published_at` **forward** (asserted on a reloaded instance); the
      text path still **preserves** `published_at` when the ad goes to `ON_MODERATION`.
      `test_edit_published_price_only_stays_published` was **rewritten**, not deleted.
- [ ] **`AD-010`** — a batch mixing a valid and an invalid id still processes the valid ad
      and reports the invalid one with a **200**; a `ValueError` from the state machine is not
      logged at `ERROR` and not reported cause-free; the response contains no raw driver text;
      an unexpected exception still produces a generic string and an `ERROR` log.
      `TestBulkLockingStructure` and phase 04's `test_bulk_ban_users_not_locked` are green.
- [ ] **`AD-011`** — after `ARCHIVED → PUBLISHED`, a **reloaded** instance has
      `archived_at is None`; the database rejects a non-`ARCHIVED` row carrying a stale
      `archived_at`.
- [ ] **`AD-012`** *(bot half)* — the failure reply contains **no** raw driver text (asserted
      over constraint name, table name, `DETAIL`, `CONTEXT`); each condition produces a
      distinct translated message; the log still carries the technical detail; the
      permission-denied message is byte-identical to today's. `test_copy_ad.py` is green
      unchanged, including phase 07's aliasing assertion.
- [ ] **`AD-013`** — the module-level `ALLOWED_TRANSITIONS` is importable and its seven source
      keys and target sets match the shipped matrix exactly. `TestTransitionValidation` and
      `TestTransitionMatrixEdges` pass **untouched**.
- [ ] **`AD-014`** — creating two `AdImage` rows for the same ad at the same position raises
      `IntegrityError`; the same position on a **different** ad is allowed;
      `test_copy_ad_image_positions_preserved` (positions `[0, 2, 5]`) passes **unchanged**;
      the Q9 pre-flight query and its result are in the commit message.
- [ ] **`AD-016`** — `submit_ad` returns a distinguishable expired-draft outcome, red first;
      the bot renders a translated, seller-recoverable message that does **not** blame the
      content; `process_preview` does **not** clear the FSM state for that outcome **and
      still does** for a genuine content failure.
- [ ] **`AD-003` / `AD-015` records** — `copy_service.py`'s docstring states the decided
      storage-key rule and the trade-off; `copy_ad`'s behaviour is unchanged; `AD-015` is
      recorded with a pointer to both owning phases.
- [ ] **`VAL-002`** — the fixture default is changed in **both** conftests; every category
      (b) producer test reaches `ON_MODERATION` through the real path; every category (a)
      consumer test passes **without** edits; a regression guard prevents the channel
      re-opening. **The census and its triage are recorded.**
- [ ] **`VAL-003`** — `bulk_approve` on a queryset containing a genuinely-approvable ad
      returns a **non-zero** count with an audit row; the approve view returns **2xx** for an
      approvable ad; a status outside the pair is rejected with an actionable message and no
      audit row; the refused-transition case surfaces the state machine's error rather than
      swallowing it. `test_approve_non_moderation_ad_returns_404` was **rewritten** and
      demonstrated red first.

### 8.4 Cross-phase integrity

- [ ] **No second patch** for `create_draft_ad` (`AD-005` / `03-DB-001`).
- [ ] **No second patch** for the `sweep_drafts` predicate or the "your draft expired"
      message (`AD-007` / `03-DB-003`).
- [ ] **No second patch** for the single-`DRAFT` rule (`AD-012` DB half / `03-DB-009`).
- [ ] **The byte-copy branch was not implemented**; `delete_adimage_files_on_delete` and
      `copy_ad`'s key reuse are unchanged.
- [ ] `AdImageService.create_or_skip` is unchanged **if** phase 07 shipped `MEDIA-002`
      first (Q6).
- [ ] `UserAdmin`, `AccountState`, `ListingsQuery.build_queryset` and `AdAdmin`'s permission
      predicates are unchanged.
- [ ] `delete_sweep.Command.handle`'s `storage_keys` pre-collection and its single-transaction
      shape are unchanged (phase 03 BLOCK 1 and BLOCK 7's).
- [ ] `record_event` is unchanged; `sweep_orphaned_media.py` is unchanged.
- [ ] `AdvisoryLockId` gained **no** new member.
- [ ] `docs/01-spec/technical-specification.md` is **unmodified** (phase 06 `PII-113`).
- [ ] Locale files were **appended** to, never regenerated wholesale.
- [ ] The ~68-citation legacy sweep was **not** started; only the three IDs inside
      `Ad.transition_to` were disambiguated.

### 8.5 Project conventions

- [ ] English only — comments, docstrings, log messages, error messages, documentation.
- [ ] No `print()`; `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
- [ ] Every fixed value is a `StrEnum` member or a module-level constant — never a bare
      string, never a dict-of-strings (project rule 10). The transition matrix and every
      retention window qualify.
- [ ] Pydantic v2 appears only at system boundaries; the Django ORM remains the persistence
      layer. No service gained an internal Pydantic model.
- [ ] All schema changes are Django migrations. No shipped migration was edited.
- [ ] Every `with transaction.atomic():` line carries the project's established
      `# pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed;
      Atomic.__enter__/__exit__ untyped` suppression, or a typed equivalent — never a bare one.
- [ ] Business logic lives in `services/`; no view, handler or `ModelAdmin` method body grew
      business logic beyond the thin boundary its block requires.
- [ ] No `apps/*` module imports `telegram_bot/*`.
- [ ] Every bot DB call remains `@sync_to_async` at `thread_sensitive=True`.
- [ ] Filesystem side effects happen only **after** commit, via `transaction.on_commit()`.
- [ ] Every non-trivial behaviour change has a test that verifies **logic and component
      interaction** — not a variable's absence, not a log string, not a line count. (BLOCK 1
      and BLOCK 14 add **no** tests, deliberately.)
- [ ] **No task target is a line number.** Every target is a file plus a semantic symbol
      (`module` / `class` / `function` / `method`) with `semantic_anchors`, per
      `.ai\tasks\templates\task_template.yaml`.
- [ ] Every task YAML carries `source_reference: .ai\plans\05-ad-lifecycle-remediation.md`
      and `source_section: "BLOCK N — <title>"`.
- [ ] `pytestmark` conventions follow the surrounding file; new test modules follow the
      existing `test_*.py` layout in the owning app.
- [ ] `uv run ruff check --fix src/` was run where imports were reordered (`ruff format` is
      not the project convention).

### 8.6 Deliverables

- [ ] The Q1, Q2, Q4, Q5 and Q6 owner decisions — or their recorded absence — are
      communicated to the coordinator. **Not silently decided.**
- [ ] The `AD-006` / `MEDIA-002` question is put to the coordinator **once**, with §5.5's
      tie-breaker (the orphaned promoted file) attached, so phase 07 does not have to
      re-derive it.
- [ ] The `0008_*` migration contention with phase 03 BLOCK 6 is resolved and recorded, and
      phase 03 is told which number phase 05 took.
- [ ] Q7's disposition is recorded even if the answer is "deferred", so the next reader
      knows `_pass_moderation`'s bare handler is a known, dated open item and not an
      oversight.
- [ ] The 18 inherited runtime claims (§0.2.4, U1–U18) are listed in the final report with
      their verification status, so the evidence-quality note is made **once**, centrally,
      rather than eighteen times across blocks.
- [ ] This plan file is updated to mark each block's completion, so the phase coordinator has
      a single status surface.
- [ ] No commit was made without an explicit user request.
