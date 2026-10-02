---
id: ad-lifecycle-remediation-record
domain: agent
tags:
  - ad-lifecycle
  - moderation
  - remediation
  - record
  - open-questions
related:
  - architecture
  - rules
  - db-schema
  - db-enums
  - db-retention
---

## Purpose

Record of the ad-lifecycle remediation pass: which blocks shipped, which decisions are still open
with the product owner, and which boundaries were deliberately left untouched. It is the single
source of truth for "we know about X and we deliberately deferred it" for this pass. The durable
behaviour itself lives in the linked database and specification docs, not here. Re-evaluate every
open gate before acting on the block it defers.

Conventions: a block is **Shipped**, **Open (owner gate)**, or **Moot**. A gate stays Open until
the owner answers it. Nothing in this record is resolved, partially resolved, or scheduled for a
named phase.

## Shipped blocks

| Block | Commit(s) | What shipped |
|---|---|---|
| 1 — transition matrix and re-publish clearing | `6e2e09d` | `ALLOWED_TRANSITIONS` hoisted to module level in `apps/ads/models.py`; `Ad.transition_to` clears `archived_at` on every `→ PUBLISHED` transition |
| 2 — publish clock on a price edit | `63937ca` | `Ad.reset_publish_clock()` owns the reset; `ad_edit`'s price-only arm resets `published_at` inside its existing single `save()` |
| 3 — honest approve outcomes | `06da133` | `ApproveOutcome` (`PUBLISHED` / `CRITERIA_REJECTED` / `TRANSITION_REFUSED`); the three approve gates widened to `{ON_MODERATION, ON_MODERATION_FAILED}`; a refused approval writes no audit row and surfaces a message instead of a 500 |
| 4 — test-factory status contract | `7f78f36`, `11d7195`, `1fe91d7`, `b3ed530` | every `create_test_ad` / `create_test_ads_bulk` call passes `status=` explicitly; regression guards in `apps/core/tests/test_ad_factory_contract.py`; moderation-queue consumers retargeted onto `ON_MODERATION_FAILED`; the factory default is now `PUBLISHED` (was `ON_MODERATION`) |
| 6A — admin change-form contract | `976b72f` | `AdAdmin` gains an explicit field contract; `AdAdminChangeForm` returns form errors instead of HTTP 500s; `save_model` branches on `change` (add vs. change) and routes a form-driven status change through the lifecycle matrix, writing exactly one `ModeratorActionLog` row through the existing moderation-log service; `Ad.transition_to` returns its source `AdStatus` |
| 8A — explicit edit allow-list | `9adafe3`, `d1827f6` | `EDITABLE_DIRECT_SAVE_STATUSES` replaces the `ad_edit` catch-all, so every other status gets a defined refusal that writes nothing; the dashboard Edit link is gated by the derived `EDIT_FORM_AVAILABLE_STATUSES` |
| 9 — bulk moderation per-ad isolation | `f29be0c` | `bulk_moderation_action` iterates `sorted(ad_ids)` with a per-ad `transaction.atomic()` plus `select_for_update()`, and names six failure classes in the new `BulkModerationError`; response keys and HTTP 200 unchanged, but the missing-ad `error` string value changed from `"Processing failed"` to `"Ad not found"` (see "Observable contract change disclosed") |
| 10 — `AdImage` position uniqueness | `ec474fe` | `uq_ad_images_ad_position` on `AdImage(ad, position)` plus migration `src/backend/apps/ads/migrations/0009_adimage_uq_ad_position.py`; contiguity deliberately not enforced |
| 12 — submission outcome vs. moderation failure | `1311021` | `SubmitAdOutcome` / `SubmitAdResult`; `process_preview` re-points the FSM at a fresh draft for a non-content failure and still clears it for a genuine content failure. The reused single expired-draft string was later replaced by one accurate reply per non-content outcome (`DRAFT_GONE` / `INVALID_TRANSITION` / `PHOTO_UNAVAILABLE`); `PHOTO_UNAVAILABLE` also clears the stale photo list and returns the seller to the photos step, so re-confirming cannot loop |

## Finding dispositions

Not every finding in this domain needed a block. These four were dispositioned
outside the block table — three retired by work that landed under another
commit, one half-shipped and still carrying an open behaviour half.

| Finding | Disposition | Commit |
|---|---|---|
| `AD-003` — `copy_ad` aliases the source ad's photo files | **Retired.** The per-key delete guard (skip `delete_photo` while another `AdImage` row still references the key) shipped in the media pass. | `64a9de6` |
| `AD-005` — `create_draft_ad`'s `IntegrityError` recovery is dead code | **Already fixed.** The recovery branch now runs inside a nested `transaction.atomic()` (SAVEPOINT), so the retry executes on a healthy connection. | `664b572` |
| `AD-007` — draft sweep uses `created_at` | **Already fixed.** Draft staleness is measured by inactivity (`updated_at`), so an active dialog is not purged mid-flow. | `2697796` |
| `AD-015` — `ads_auto_publish=False` does not hide the seller's published ads | **Half shipped.** The `UserAdmin` field-contract half shipped (`a19a0ee`); the **behaviour half is still open and unowned** — flipping `ads_auto_publish=False` still does not hide the ad, because `ListingsQuery.build_queryset` consults only `user__is_declined`. **This needs an owner.** | field contract: `a19a0ee`; behaviour: none |

## Open owner gates

All five are unanswered. A deferred block is not approved, not partially approved and not
scheduled.

| Gate | Question | Deferred block | State |
|---|---|---|---|
| Q1 | May a moderator move an ad's `status`, and through which seam? | BLOCK 6B, making `status` read-only | Open. `status` is deliberately still editable after 6A |
| Q2 | How should `ON_MODERATION` be made durably committable? | BLOCK 5 (`AD-008`) | Open. No code shipped |
| Q4 | Which retention anchor is correct for `delete_sweep`? | BLOCK 7 (`AD-004`, `VAL-005`) | Open. No code shipped; the sweep still filters on `archived_at` |
| Q5 | What may a seller do to an auto-failed ad: re-moderate, refuse, or hide the affordance? | BLOCK 8B | Open. `purge_failed_ads`' 7-day timer is still not reset, and no `ON_MODERATION_FAILED → ON_MODERATION` matrix edge was added |
| Q6 | Is `MEDIA-002`'s promoted-file reclaim in scope? | BLOCK 13 (`AD-006`) | Open. No code shipped |

### Work owed to BLOCK 6B

The Validator flagged ~95 lines of lifecycle policy concentrated in
`AdAdmin.save_model` / `AdAdmin._apply_status_change` /
`AdAdminChangeForm.clean` against project rule 3 (separation of concerns).
Extracting that policy into a service is **recommended as part of BLOCK 6B**,
not now: the write-path decision is exactly Q1's subject matter, and Q1 is an
unanswered owner gate. BLOCK 6B should extract the admin lifecycle policy into a
service while it decides Q1. **This phase deliberately did not perform the
extraction.**

## Moot blocks

- **BLOCK 11 is moot.** The bot-message half of `AD-012` already shipped as `ba1b059`: the
  `_("Failed to copy ad.")` message, its translations and a test. Do not record it as new work.

## Boundaries deliberately left untouched

| Boundary | Why it is still absent |
|---|---|
| No reverse `CheckConstraint` on `archived_at` | The six `AD-001` presence constraints stay one-way. `transition_to` clears the column on `→ PUBLISHED`; the database does not police its absence elsewhere |
| No `ON_MODERATION_FAILED → PUBLISHED` matrix edge | Refused by design. The real publish path for a failed ad depends on Q5 (BLOCK 8B) |
| No `ModeratorActionLog.moderator` column | The audit row keeps `user_id` (SET NULL on erasure) as its only actor FK. Routing the admin form's status change through the existing service does not imply a new column |
| `AdImage` contiguity not enforced | `uq_ad_images_ad_position` guarantees uniqueness within one ad and nothing more; gaps are permitted and preserved, because `copy_ad` carries a source ad's positions such as `[0, 2, 5]` through verbatim |
| `search_vector*` fields excluded, not read-only | The `ads_search_vector_update` trigger rewrites all four columns on every write, so they are dropped from the admin form. Rendering them read-only would advertise editable data that the database then discards |
| `VAL-001`'s fourth bare audit ID left in `db-schema.md` | `docs/02-database/db-schema.md`'s `archived_at` line still carries a cycle-ambiguous `AD-005` in a comment. The phase appended to that line but deliberately left the bare ID in place: it belongs to the repository-wide legacy-ID sweep and to phase 03, and removing it is gated on a coordinator decision |

## Observable contract change disclosed

| Surface | What changed | Disclosed in |
|---|---|---|
| Bulk moderation endpoint per-id `error` value | The response shape (`{"completed", "errors": [{"id", "error"}]}`) and the HTTP 200 are unchanged, but the **string value** for a missing ad changed from the generic `"Processing failed"` to `"Ad not found"`. Out-of-repo consumers keying on that literal must update. | `f29be0c` (AD-010) |


## Where the shipped behaviour is documented

| Fact | Durable document |
|---|---|
| Transition matrix (7 source keys), terminal states, `ON_MODERATION_FAILED → PUBLISHED` refused | [db-schema.md](../02-database/db-schema.md) |
| `archived_at` cleared on re-publish; the six one-way `CheckConstraint`s | [db-schema.md](../02-database/db-schema.md), [db-indexes.md](../02-database/db-indexes.md) |
| `uq_ad_images_ad_position`, gaps permitted, migration 0009 | [db-schema.md](../02-database/db-schema.md) |
| AD-003 per-key delete guard, retired as `64a9de6` | [db-schema.md](../02-database/db-schema.md), [db-retention.md](../02-database/db-retention.md) |
| Sweep retention values and the `delete_sweep` anchor, with Q4 open | [db-retention.md](../02-database/db-retention.md) |
| `ApproveOutcome`, `BulkModerationError`, the unchanged bulk response shape | [db-enums.md](../02-database/db-enums.md) |
| `published_at` reset on reactivation and on a price-only edit | [db-schema.md](../02-database/db-schema.md), [seller-stories.md](../04-user-stories/seller-stories.md) |
| Admin form audit row and the seller-side edit refusal | [admin-stories.md](../04-user-stories/admin-stories.md), [seller-stories.md](../04-user-stories/seller-stories.md) |
| Test-factory status contract and its guard test | [rules.md](rules.md) |
