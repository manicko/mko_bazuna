---
name: 05-ad-lifecycle
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 05 — Ad Lifecycle, Categories & Moderation

> **Auditor handbook.** Audit the ad entity lifecycle, the category tree, and the
> moderation gate of a dual-process (web + bot) Django classifieds system.
> Work strictly through architectural layers, zones of responsibility, and the
> discovery + runtime-verification steps below. Do **not** reference specific
> files, modules, classes, or functions — reason only about generalized layers
> and entities described here.

## Output mode

`problems-only: true` — this phase reports **only findings**:

- Emit **only** failing checks. Omit any row that passes.
- If nothing fails, emit a single line: `No problems found in this phase.`
- Each finding = **runtime evidence** (what was observed/executed) + **exact
  consequence** (what breaks in production).
- Finding IDs are prefixed `AD-`.

---

## Purpose

Reusable procedure for auditing:

1. The **ad entity** and its **state machine** (status enum + legal transitions
   with atomic side-effects).
2. The **bot ad-creation FSM**, durably persisted as DRAFT ad rows so a dialog
   survives restart/crash.
3. The **moderation gate** — an automatic pre-publish check that is the *only*
   gate before an ad becomes public (moderator = admin role).
4. The **category tree** — a closed, admin-managed hierarchical structure used
   for classification and search.
5. The **photo-collection** entity — 1–5 ordered photos attached per ad.
6. The **purge/sweep jobs** — retention-window cleanup of failed, rejected,
   draft, archived, and deleted ads.

### State machine (as-is)

| Status | Meaning |
|--------|---------|
| `DRAFT` | Bot FSM in progress (durable). |
| `ON_MODERATION` | Submitted, awaiting auto-check approval. |
| `PUBLISHED` | Approved and publicly visible. |
| `REJECTED` | Auto-check failed, held for retention then purged. |
| `ON_MODERATION_FAILED` | Auto-check could not complete; queued for purge. |
| `ARCHIVED` | Hidden but retained; reactivatable. |
| `DELETED` | Soft-deleted; retained then purged. |

Legal transitions:

- `DRAFT → ON_MODERATION` (submit)
- `ON_MODERATION → PUBLISHED` (approve) · `ON_MODERATION → REJECTED` (reject)
- `ON_MODERATION → ON_MODERATION_FAILED` (check error)
- `PUBLISHED → ARCHIVED` · `ARCHIVED → PUBLISHED` (reactivate)
- `PUBLISHED → ON_MODERATION` (text-edit re-hide + re-moderate)
- `any → DELETED`

### Retention windows (purge/sweep)

| Status | Retention | Action |
|--------|-----------|--------|
| `ON_MODERATION_FAILED` | 7 days | purge |
| `REJECTED` | 90 days | purge |
| `DRAFT` | 30 minutes | purge |
| `ARCHIVED` | 2 months | purge |
| `DELETED` | 4 months | purge |

---

## Architectural layers

| Layer | Zone of responsibility | Key risks |
|-------|------------------------|-----------|
| **Ad entity + status enum** | Lifecycle timestamps, the status field, and its enumeration. | Invalid/forbidden transition permitted; status overwritten without side-effects; wrong lifecycle timers (`published_at`, `original_published_at`, archive/delete). |
| **State-machine driver / transition zone** | Centralized valid-transitions registry + atomic side-effects. | Direct status overwrite bypassing the driver; partial updates; non-atomic side-effects. |
| **Bot FSM + DRAFT-persistence zone** | Durable dialog persisted as DRAFT rows. | Orphaned DRAFT on cancel/crash; concurrent-edit/session safety; partial DRAFT. |
| **Moderation-gate zone** | Auto-check as the only gate before PUBLISHED. | Gate bypassed → unmoderated content public; over-blocking valid ads; non-admin moderator; failed→purge path missing. |
| **Category-tree zone** | Closed, admin-only hierarchical classification + search. | Cycles; orphan nodes; wrong parent; inactive category mis-used; rename not propagated. |
| **Photo-collection zone** | 1–5 ordered photos attached to the correct ad. | Count/order violations; attachment to wrong ad; non-atomic photo+ad create. |
| **Purge/sweep zone** | Retention-window cleanup of each terminal status. | Wrong rows purged; active rows unsafe; timezone/retention errors; no lock. |

---

## Discovery stage

Map each layer to its implementation. Report gaps as findings.

1. **Ad entity + status-enum mapping** — enumerate all statuses and the legal
   transitions; map every lifecycle timestamp field to its transition.
2. **State-machine driver mapping** — locate the transition service; verify
   *all* transitions pass through it; find any direct status assignment that
   bypasses it.
3. **FSM + DRAFT mapping** — trace the bot dialog to a DRAFT row; confirm
   cancel/crash cleanup; confirm concurrent post/session safety.
4. **Moderation-gate mapping** — locate the auto-check; verify it is the *only*
   gate before PUBLISHED; verify moderator-role enforcement; verify the
   failed→purge path.
5. **Category-tree mapping** — verify closed/admin-only; verify tree invariants;
   verify rename propagation to dependent ads (denormalized name + search vector).
6. **Photo-collection mapping** — verify count/order validation; verify the
   attachment foreign key; verify atomic photo+ad creation.
7. **Purge/sweep mapping** — for each job verify its status filter, retention
   window, and lock; verify active rows are excluded.

---

## Mandatory runtime verification

Run **before** the checklist. Capture concrete evidence for every item.

- **R1 — Full transition matrix.** Drive an ad through *every* legal transition.
  Verify side-effects: `published_at` set; `original_published_at` set only on
  *first* publish; lifecycle timers reset on *every* PUBLISHED transition;
  `archived_at` cleared on reactivate; `search_vector` recomputed on text-edit.
- **R2 — Forbidden transitions.** Attempt illegal jumps — `DRAFT→PUBLISHED`,
  `ON_MODERATION→PUBLISHED` without approve, `ON_MODERATION_FAILED→PUBLISHED`,
  `REJECTED→PUBLISHED`, `PUBLISHED→ON_MODERATION` bypassing text-edit. All must
  be rejected.
- **R3 — Moderation bypass.** Attempt to publish without passing auto-check →
  rejected. Verify no unpublished (`DRAFT`/`ON_MODERATION`/`ON_MODERATION_FAILED`)
  ad appears in public listings or search.
- **R4 — FSM DRAFT cleanup.** Start a dialog, then cancel/crash. Verify the
  DRAFT row and its photos are cleaned. Verify only correct DRAFTs are purged at
  the 30-minute window.
- **R5 — Category integrity.** Attempt cycle/orphan/closed-tree public write →
  rejected or detected. Rename a category → verify the denormalized name and
  search vector propagate to subtree ads.
- **R6 — Purge/sweep correctness.** Seed ads at each retention boundary; run
  each sweep. Verify ONLY correct rows removed, active rows safe, CASCADE photos
  removed. Run each sweep twice → idempotent.
- **R7 — Static + test suite.** Run the linter, the type-checker, and the
  lifecycle/moderation/category/photo test-suite. Record failures.

---

## Audit dimensions

### (a) State-machine integrity
| Check | Description | Evidence required |
|-------|-------------|-------------------|
| A1 | All transitions valid and mutually exclusive. | R1 + R2 traces. |
| A2 | No direct status overwrite bypassing the driver. | Discovery #2; grep for direct status assignment. |
| A3 | Side-effects atomic with status change (single transaction). | R1 per-transition; transaction boundary proof. |
| A4 | Lifecycle timestamps correct. | R1: `published_at`, `original_published_at`, archive/delete timers, text-edit re-hide + re-moderation. |

### (b) FSM-as-DRAFT persistence
| Check | Description | Evidence required |
|-------|-------------|-------------------|
| B1 | Dialog resumable across restart. | Restart mid-FSM; resume succeeds. |
| B2 | Orphaned DRAFTs cleaned (cancel + sweep). | R4. |
| B3 | Concurrent post/session cannot corrupt or duplicate a user's DRAFT. | Concurrent dialog test. |
| B4 | No partial DRAFT on crash. | Crash mid-FSM; integrity check. |

### (c) Moderation-gate correctness
| Check | Description | Evidence required |
|-------|-------------|-------------------|
| C1 | Auto-check is the ONLY gate before PUBLISHED. | Discovery #4; R3. |
| C2 | Moderator role = admin enforced. | Attempt moderate as non-admin. |
| C3 | Failed → `ON_MODERATION_FAILED` → purge. | R6 boundary for failed. |
| C4 | Generic seller-facing errors (no internal reason leak). | Inspect seller-facing message on reject. |
| C5 | No over-blocking of valid ads. | Valid ad passes on first submit. |

### (d) Category-tree integrity
| Check | Description | Evidence required |
|-------|-------------|-------------------|
| D1 | Closed/admin-only (no public write). | Discovery #5; public-write attempt. |
| D2 | No cycles/orphans. | R5. |
| D3 | Correct hierarchy used for classification + search. | Search-by-category test. |
| D4 | `is_active` correctly hides/shows. | Inactive-category ad absent from listings. |
| D5 | Rename propagates denormalized name + search vector. | R5. |

### (e) Photo-collection rules
| Check | Description | Evidence required |
|-------|-------------|-------------------|
| E1 | 1–5 count enforced at validation. | Submit with 0 and 6 photos. |
| E2 | Position/ordering preserved. | Verify stored order matches upload order. |
| E3 | Attached to correct ad via FK. | Inspect FK integrity. |
| E4 | Photo+ad creation atomic. | No ad with 0 photos published; no orphaned image files. |

### (f) Purge/sweep correctness
| Check | Description | Evidence required |
|-------|-------------|-------------------|
| F1 | Each job purges ONLY its status at its retention window. | R6 boundaries. |
| F2 | Active/published/archived rows ALWAYS safe. | R6: active rows survive all sweeps. |
| F3 | Timezone-aware datetimes. | Inspect retention comparison logic. |
| F4 | Advisory lock prevents concurrent/duplicate runs. | Run sweep twice concurrently. |
| F5 | CASCADE photo files cleaned. | R6: photos gone with purged ad. |

---

## Cross-cutting concerns (owned here)

- **Transition atomicity** — Phase 03 owns the *mechanism*; **this phase owns the
  correctness** of each transition's side-effects.
- **FSM DRAFT + consent** — when a seller revokes consent mid-dialog (Phase 06),
  DRAFT rows and photos must be purged with no PII remaining.
- **Category rename → search vector** — Phase 08 depends on the denormalized
  name being correct; propagation is owned here.
- **Photo rules vs media** — Phase 07 owns file handling; **this phase owns**
  count/order/attachment correctness.

---

## Severity taxonomy

| Severity | Examples (not exhaustive) |
|----------|---------------------------|
| **CRITICAL** | Forbidden transition allowed / direct status overwrite bypassing the driver; moderation gate bypassed (unmoderated content public); wrong `published_at`/lifecycle timer (wrong archive/delete); active ad purged; category cycle/orphan corrupting classification+search; FSM DRAFT orphaned leaking PII/blocking. |
| **HIGH** | Photo count/order violated or attached to wrong ad; purge timing wrong (failed too late / rejected too early); moderation over-blocks; missing side-effect on transition; non-admin can moderate. |
| **MEDIUM** | Orphaned DRAFT not cleaned; category rename not propagated; missing transaction around transition; no re-moderation on text-edit; concurrent FSM session unsafe. |
| **LOW** | Log verbosity; missing type hints. |

---

## Edge-case checklist

- Concurrent edit while `ON_MODERATION`.
- Bot crash mid-FSM leaving a DRAFT.
- Category deleted while ads reference it.
- Photo upload fails, leaving an ad without its required photo.
- Text-edit on `PUBLISHED` must re-hide + re-moderate.
- Purge runs while an ad transitions.
- Retention boundaries: `REJECTED@90d` / `FAILED@7d` / `DRAFT@30min` /
  `ARCHIVED@2mo` / `DELETED@4mo`.
- Seller deletes then re-creates.

---

## Isolation / test note

- Lifecycle tests use synthetic data.
- Simulate forbidden transitions — they must raise or be ignored.
- Verify purge idempotency (run each sweep twice).
- Verify unpublished ads never appear in listings.

---

## Dead-code note

Transition, moderation, purge, or cleanup utilities that are defined but never
wired into the lifecycle are findings.

---

## Report output

Write findings to `.ai/audit/05-ad-lifecycle/findings.md` using the template
`.ai/audit/templates/audit-findings.md`.

- Append incrementally (≤100 lines).
- Prefix every finding `AD-`.
- Restate `problems-only` rules: only findings; omit passing rows; if none →
  `No problems found in this phase.`; each finding = runtime evidence + exact
  consequence.
