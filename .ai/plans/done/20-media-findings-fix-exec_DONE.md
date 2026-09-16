---
id: media-findings-fix-exec
domain: plan
source: .ai/audit/99-validation/07-media-validated-findings.md
verification: .ai/audit/99-validation/07-media-verification-report.md  # NOTE: file does not exist — see §0.6
tags:
  - media
  - audit-fix
  - cr-001
  - high-001
  - high-002
  - med-001
  - med-002
  - med-003
  - low-001
  - low-002
  - low-003
  - low-004
related:
  - .ai/audit/99-validation/07-media-validated-findings.md
  - .ai/tasks/templates/task_template.yaml
  - docs/02-database/db-retention.md
  - docs/02-database/db-indexes.md
  - docs/01-spec/technical-specification.md
  - docs/04-user-stories/seller-stories.md
  - src/telegram_bot/handlers/ad_create.py
  - src/backend/apps/ads/models.py
  - src/backend/apps/ads/views/listings.py
  - src/backend/apps/media/services/filesystem.py
  - src/backend/apps/media/management/commands/sweep_orphaned_media.py
  - src/backend/apps/core/management/commands/sweep_drafts.py
  - src/backend/apps/ads/services/submission.py
  - src/backend/apps/moderation/signals.py
  - src/backend/apps/moderation/services/auto_moderation.py
  - src/backend/apps/media/apps.py
  - src/telegram_bot/tests/test_ad_create.py
  - src/backend/apps/media/tests/test_sweep_orphaned_media.py
  - src/backend/apps/core/tests/test_sweep_commands.py
  - src/backend/apps/ads/tests/test_media_security.py  # CORRECTED: was media/tests/test_media_security.py
---

# Execution Plan 20 — Media Subsystem Findings Fix (Refined)

> **Source:** `.ai/audit/99-validation/07-media-validated-findings.md` (72 validated
> findings, 10 VALIDATED + 1 RESOLVED)
>
> **Refined from:** `.ai/plans/20-media-findings-fix.md` (untracked plan)
>
> This plan supersedes the original. It incorporates the Auditor's findings about
> the working-tree state, corrected test paths/names, and dependency corrections.

---

## 0. Corrections & Auditor Findings Summary

The Auditor verified the codebase state against the original plan and identified
the following discrepancies that change task definition and ordering. Each is
addressed in this refined plan:

### 0.1 B1 is already implemented in the working tree (uncommitted)

`src/telegram_bot/handlers/ad_create.py` working tree contains **all three** B1
fix points. `git diff HEAD` confirms:

- `cmd_cancel` now has the `AdStatus.DRAFT` guard + `_get_ad_status()` helper
  (working-tree lines 106–135). HEAD still has `"""Cancel ad creation."""` with
  no guard.
- `process_preview` success path calls `await state.clear()` (working-tree line 859).
  HEAD has `state.clear()` only on the failure path.
- `delete_draft` iterates `img.storage_keys()` instead of `img.image`
  (working-tree lines 952–954). HEAD calls `delete_photo(img.image)`.
- The `_get_ad_status` helper already exists (working-tree lines 914–933).

**B1 Implementor task is NOT to re-implement.** It is:
1. Commit `ad_create.py` working-tree changes only (exclude the unrelated
   PII-consent working changes in `consent_record.py`, `login.py`,
   `__init__.py`, `main.py`, `.po` files, and the new `consent.py` handler).
2. Add the missing B1 regression tests (none exist — see §0.2).
3. Validate via the test suite.

### 0.2 B1 regression tests do not exist

`src/telegram_bot/tests/test_ad_create.py` contains only
`TestProcessPreviewLanguageDetection` and `TestProcessPhotos`. There are **no**
cancel-after-submit or `delete_draft` tests. B1 requires adding these.

### 0.3 Test file path correction (B6, B7, B9)

The original plan's top-level `related:` list cites
`src/backend/apps/media/tests/test_media_security.py` — **this path is wrong**.
The actual file is at:

```
src/backend/apps/ads/tests/test_media_security.py
```

All block-level citations must use the correct path. Confirmed via `git ls-files`:
- `src/backend/apps/ads/tests/test_media_security.py` — exists and is tracked
- `src/backend/apps/media/tests/test_media_security.py` — does not exist

### 0.4 Corrected test class / method names

| Original plan reference | Actual name | Location |
|---|---|---|
| `TestProcessPreview` (B1 acceptance criteria) | `TestProcessPreviewLanguageDetection` | `src/telegram_bot/tests/test_ad_create.py:94` |
| `test_orphaned_file_deleted` (B8) | `test_orphaned_file_is_deleted` | `test_sweep_orphaned_media.py:52` |
| `test_seed_files_preserved` (B8) | `test_seed_subdir_excluded` | `test_sweep_orphaned_media.py:103` |

### 0.5 B7 and B9 share `_serve_image` — ordering constraint

Both B7 and B9 edit the `_serve_image` function in
`src/backend/apps/ads/views/listings.py`. B7 changes the return from
`HttpResponse(data, ...)` to `FileResponse(open(...))`. B9 adds cache-control
headers on the response returned by `media_gate` (which calls `_serve_image`
in DEBUG mode). **B7 must ship before B9**; B9 must target the `FileResponse`
return type that B7 introduces.

### 0.6 Verification report does not exist

The plan frontmatter and §5 cite
`.ai/audit/99-validation/07-media-verification-report.md`. This file does **not**
exist in the working tree. The Auditor's findings (in §0) are the authoritative
source of validation status. This note is recorded here for traceability; no
verification-task change is implied beyond using the Auditor's findings directly.

### 0.7 `IX_ads_pub_condition` advisory (out of scope for B5)

`docs/02-database/db-indexes.md:35-39` documents a partial index named
`IX_ads_pub_condition` on `listing_condition_id` (condition: PUBLISHED).
This index **does not exist** in `Ad.Meta.indexes` (confirmed at
`models.py:256-324` — the Ad model's indexes do not include it). The only
`listing_condition_id` indexing is via the `FK` default. This is an advisory
discrepancy; B5 scope is limited to AdImage lookup-field indexes. B5's Doc-
specialist should note this discrepancy but should **not** attempt to create
the missing `IX_ads_pub_condition` index (different model, different scope).

---

## 1. Resolution Status & Scope

| ID | Finding | Severity | Status | Action |
|---|---|---|---|---|
| CR-001 | Cancel after submit destroys ad images | CRITICAL | CONFIRMED — **in working tree, uncommitted** | Commit + add regression tests + validate (Block B1) |
| HIGH-001 | No file cleanup on AdImage cascade-delete | HIGH | CONFIRMED — not implemented | Implement (Block B2) |
| HIGH-002 | Orphan sweep deletes in-flight uploads | HIGH | CONFIRMED — not implemented | **Gate R-001 RESOLVED** (staging dir, move-before-TX, TTL for abandoned) → Implement (Block B3) |
| MED-001 | `delete_draft` doesn't delete thumbnails | MEDIUM | CONFIRMED — **already fixed** in working tree (part of B1) | Bundled with B1 commit + tests |
| MED-002 | Telegram download before size validation | MEDIUM | CONFIRMED — not implemented | Implement (Block B4) |
| MED-003 | No DB indexes on AdImage lookup fields | MEDIUM | CONFIRMED — not implemented | Implement (Block B5) |
| MED-004 | DRAFT retention mismatch (30 min vs 7 days) | — (doc) | **RESOLVED** — doc already says "30 minutes" at `db-retention.md:32` and `:82`; code at `sweep_drafts.py:45` uses `timedelta(minutes=30)` | **Skip — no change needed** |
| LOW-001 | Incomplete EXIF strip (icc_profile) | LOW | CONFIRMED — not implemented | Implement (Block B6) |
| LOW-002 | `_serve_image` docstring/code mismatch | LOW | CONFIRMED — not implemented | Implement (Block B7) |
| LOW-003 | Dead code in `_walk_media_files` | LOW | CONFIRMED — not implemented | Implement (Block B8) |
| LOW-004 | No cache-control on media_gate | LOW | CONFIRMED — not implemented | Implement (Block B9) |

**MED-004 is excluded from implementation.** Verified: `db-retention.md:32`
says "30 minutes" for DRAFT retention, `db-retention.md:82` says "30 minutes"
for the `sweep_drafts` default, and `sweep_drafts.py:45` uses
`timedelta(minutes=30)`. Documentation and code are aligned. No change needed.

**10 findings → 9 execution blocks.** CR-001 and MED-001 are bundled (Block B1)
because they touch the same cancel-flow code path and are already shipped together
in the working tree.

---

## 2. Block Summary Table

| Block | ID | Findings | Scope | Agent(s) | Risk | Order |
|---|---|---|---|---|---|---|
| B1 | TX-001 | CR-001, MED-001 | `ad_create.py` — `cmd_cancel`, `_get_ad_status`, `process_preview`, `delete_draft` + regression tests | Implementor | High | 1 |
| B2 | TX-002 | HIGH-001 | New `media/signals.py`, `media/apps.py` registration, `AdImage` model | Implementor | Low | 1 (parallel) |
| B3 | TX-003 | HIGH-002 | `save_photo` staging, `submission.py` move, `sweep_orphaned_media.py` exclusion + TTL | Implementor (Gate R-001 ✓) | Medium-High | 2 (after B1) |
| B4 | TX-004 | MED-002 | `ad_create.py` — `process_photos` file_size pre-check | Implementor | Low | 1 (parallel) |
| B5 | TX-005 | MED-003 | `AdImage.Meta.indexes` + migration + `db-indexes.md` | Implementor | Low | 1 (parallel) |
| B6 | TX-006 | LOW-001 | `filesystem.py` — `strip_photo_exif` icc_profile | Implementor | None | 1 (parallel) |
| B7 | TX-007 | LOW-002 | `listings.py` — `_serve_image` FileResponse swap | Implementor → Doc-specialist | None | 1 (parallel) |
| B8 | TX-008 | LOW-003 | `sweep_orphaned_media.py` — dead code in `_walk_media_files` | Implementor | None | 1 (parallel) |
| B9 | TX-009 | LOW-004 | `listings.py` — `media_gate` cache-control headers | Implementor → Validator | Low | 3 (after B2, B7) |

---

## 3. Phase / Ordering

The execution is organized into three phases. Phases 1 and 2 are parallelizable
within their constraints. Phase 3 (B9) is ordered after B2 and B7 per the
Auditor's corrections (§0.5, §0.7).

```
Phase 1 (Risk-critical + independent, parallel-safe, single Implementor):
    B1 (CR-001 + MED-001)    ──► commit working-tree changes → add regression
                                            tests → validate
    B2 (HIGH-001)            ──► model safety net; enables safer B9 cache policy
    B4 (MED-002)             ──► trivial pre-check; reduces memory exhaustion now
    B5 (MED-003)             ──► migration; independent
    B6 (LOW-001)             ──► trivial
    B7 (LOW-002)             ──► trivial; Doc-specialist verifies docstring
    B8 (LOW-003)             ──► trivial dead code removal

Phase 2 (Research gate RESOLVED — can overlap Phase 1 after B1 ships):
    B3 (HIGH-002)            ──► Gate R-001 ✓ ──► Implementor ──► Validator
    (B3 touches save_photo in ad_create.py — must not conflict with B1's
     commit step; B3 implementation starts only after B1 is committed)

Phase 3 (depends on B2's file-deletion guarantee AND B7's FileResponse change):
    B9 (LOW-004)             ──► Validator review (cache policy + auth variance)
    Depends on: B2 (prompt file deletion → long max-age is safe)
    Depends on: B7 (FileResponse return type in _serve_image)
```

**Key ordering constraints (from Auditor findings):**

1. **B1 ships first** — only if B1's working-tree code is committed first, B3's
   `save_photo` edits in the same file can be cleanly sequenced. The Implementor
   must commit B1's `ad_create.py` changes before editing `save_photo` for B3.
2. **B9 ships after B2** — long `max-age=31536000, immutable` cache is safe only
   when B2's `pre_delete` signal ensures prompt file deletion on ad status change.
   If B2 has not deployed, B9 must use a conservative short `max-age` (e.g. 3600)
   with revalidation.
3. **B9 ships after B7** — both edit `_serve_image` in `listings.py`. B7 must
   complete first so B9's cache-header logic targets the `FileResponse` return
   type. This is a hard ordering constraint (shared-edit risk), not a soft
   dependency.
4. **B3 has a mandatory Researcher gate** — see §5, Gate R-001.
5. **B1, B2, B4, B5, B6, B8 are fully independent** — no inter-block dependencies.

---

## 4. Dependency DAG

```
                     ┌──► B2 (HIGH-001) ──► B9 (LOW-004)
                     │
    ┌─── B1 (commit ─┤
    │   + tests)     │                      ┌──► B7 (LOW-002) ──► B9 (LOW-004)
    │                 │
    │                 │                      ┌──► B4 (MED-002)
    ├──► Phase 1:     │                      ├──► B5 (MED-003, migration)
    │   B6 (LOW-001)  │                      ├──► B6 (LOW-001)
    │   B8 (LOW-003)  │                      └──► B8 (LOW-003)
    │                 │
    │                 └──► B3 (HIGH-002, Researcher gate)
    │                          (overlaps Phase 1 after B1 commit)
    │
    └─── Phase 2 / Phase 3 (sequenced)

B9 depends_on: [b2_adimage_signal, b7_serve_image_fix]
```

---

## 5. Per-Block Detail

Each block below follows the `task_template.yaml` structure
(`.ai/tasks/templates/task_template.yaml`): `id`, `title`, `priority`,
`depends_on`, `source_reference`, `description`, `goals`, `files`, `changes`,
`acceptance_criteria`, `risks`, `agents`, `implementation_sequence`.

---

### Block B1 — TX-001: Commit B1 Working-Tree Changes + Add Regression Tests

**Findings:** CR-001 (CRITICAL, SPEC-DEVIATION), MED-001 (MEDIUM, BEST-PRACTICE)

**Status:** B1 LOGIC IS ALREADY IMPLEMENTED in the working tree of
`ad_create.py` (confirmed via `git diff HEAD`). This block commits the code +
adds the missing regression tests + validates. Do NOT re-implement.

**Source reference:**
`.ai/audit/99-validation/07-media-validated-findings.md` → "CR-001: Cancel after
successful submit destroys ad images" and "MED-001: delete_draft does not delete
thumbnail files"

```yaml
id: b1_cancel_flow_fix
title: Commit B1 working-tree changes in ad_create.py + add cancel-after-submit and delete_draft regression tests
priority: critical
depends_on: []
source_reference: .ai/plans/20-media-findings-fix.md
source_section: Block B1 — TX-001: Cancel-Flow Data-Loss Fix
source_blocks:
  - "CR-001: process_preview success path calls state.clear()"
  - "CR-001: cmd_cancel has AdStatus.DRAFT guard + _get_ad_status helper"
  - "CR-001: delete_draft early-returns on non-DRAFT"
  - "MED-001: delete_draft uses img.storage_keys() (already in working tree)"

description: >
  The B1 fix (state.clear() on success, cmd_cancel DRAFT guard, storage_keys()
  in delete_draft) is already present in the working-tree version of
  ad_create.py but has NOT been committed. HEAD still has the buggy version
  (docstring "Cancel ad creation.", no guard, delete_photo(img.image),
  state.clear() only on failure path).

  The _get_ad_status helper (working-tree lines 914-933) is already present and
  need not be re-added.

  Additionally, no B1 regression tests exist in test_ad_create.py (only
  TestProcessPreviewLanguageDetection and TestProcessPhotos are present).

  This block's Implementor task is:
  1. Commit ONLY the ad_create.py working-tree changes (isolate from the
     unrelated PII-consent changes: consent_record.py, login.py, __init__.py,
     main.py, .po files, consent.py).
  2. Add regression tests for cancel-after-submit and delete_draft.
  3. Validate via the test suite.

goals:
  - commit ad_create.py working-tree B1 changes (state.clear, cmd_cancel guard,
    delete_draft storage_keys) — NOT the PII-consent changes
  - add regression test: submit ad to ON_MODERATION/PUBLISHED → send /cancel →
    assert original files + thumbnails still exist on disk and AdImage rows intact
  - add regression test: delete_draft on DRAFT ad with AdImage rows + thumbnails →
    assert all storage_keys() deleted via delete_photo
  - validate: full test_ad_create.py suite passes
  - prevent any data loss on cancel-after-submit

files:
  - path: src/telegram_bot/handlers/ad_create.py
    targets:
      - type: function
        name: process_preview       # success path: state.clear() (already in working tree)
      - type: function
        name: cmd_cancel            # DRAFT guard + _get_ad_status (already in working tree)
      - type: method
        name: _get_ad_status        # helper (already in working tree, lines 914-933)
      - type: function
        name: delete_draft          # uses storage_keys() (already in working tree)
  - path: src/telegram_bot/tests/test_ad_create.py
    targets:
      - type: class
        name: TestProcessPreviewLanguageDetection  # existing class (not "TestProcessPreview")
      - type: class
        name: TestProcessPhotos                    # existing class
      - type: class
        name: TestCancelAfterSubmit                # NEW — to be added

changes:
  - action: commit
    description: >
      Stage and commit ONLY src/telegram_bot/handlers/ad_create.py. The working
      tree contains additional uncommitted PII-consent changes
      (consent_record.py, login.py, handlers/__init__.py, main.py, .po files,
      new consent.py handler) that belong to a separate block/phase and must NOT
      be committed here.

      Use selective staging:
        git add src/telegram_bot/handlers/ad_create.py
        git commit -m "fix(media): guard cmd_cancel against non-DRAFT ads, clear FSM state on submit, use storage_keys() in delete_draft"
      Then `git status` to confirm no other files are staged.

  - action: add_code
    description: >
      Add regression test class TestCancelAfterSubmit to test_ad_create.py with:
      (a) cancel_after_submit_preserves_files: create DRAFT ad with AdImage
      (image + thumbnails on disk), submit to ON_MODERATION/PUBLISHED via
      submit_ad, then call cmd_cancel → assert files still exist, AdImage rows
      intact.
      (b) cancel_after_submit_logs_skip: assert that _get_ad_status is queried
      and the non-DRAFT path logs "Cancel skipped" without calling delete_photo.

  - action: add_code
    description: >
      Add regression test for delete_draft using storage_keys():
      create_draft_ad → attach photos to FSM state → call delete_draft →
      assert delete_photo called for ALL keys returned by img.storage_keys()
      (original + 3 thumbnails), not just img.image.

acceptance_criteria:
  - ad_create.py working-tree B1 changes are committed (git log shows new commit)
  - ad_create.py is the ONLY source file in that commit (PII-consent files NOT staged)
  - TestCancelAfterSubmit.test_cancel_after_submit_preserves_files: files + AdImage
    rows survive cancel after submit
  - TestCancelAfterSubmit.test_cancel_after_submit_logs_skip: non-DRAFT path skips
    delete_photo
  - delete_draft test: delete_photo called for all storage_keys() (original +
    thumbnails), not just img.image
  - full test_ad_create.py suite passes (TestProcessPreviewLanguageDetection,
    TestProcessPhotos, TestCancelAfterSubmit, TestDeleteDraftStorageKeys)

required_tests:
  - test: submit ad to ON_MODERATION → send /cancel → assert original files +
    thumbnails still exist on disk, AdImage rows intact
    file: src/telegram_bot/tests/test_ad_create.py
    class: TestCancelAfterSubmit
  - test: cancel after submit does NOT call delete_photo (non-DRAFT path)
    file: src/telegram_bot/tests/test_ad_create.py
    class: TestCancelAfterSubmit
  - test: delete_draft on DRAFT ad with AdImage + thumbnails → assert delete_photo
    called for all storage_keys()
    file: src/telegram_bot/tests/test_ad_create.py
    class: TestDeleteDraftStorageKeys

implementation_sequence:
  1. Verify working-tree B1 changes are correct (re-read git diff for ad_create.py)
  2. git add src/telegram_bot/handlers/ad_create.py (ONLY this file)
  3. git commit with descriptive message
  4. git status — confirm no PII-consent files staged
  5. Add TestCancelAfterSubmit class to test_ad_create.py
  6. Add TestDeleteDraftStorageKeys class to test_ad_create.py
  7. Run: $dc run --rm -e PYTEST_OPTS="-k TestCancelAfterSubmit or -k TestDeleteDraftStorageKeys" test
  8. Run full test_ad_create.py suite

risks:
  - High: behavioral change — `/cancel` no longer deletes media for non-DRAFT ads.
    This is the correct behavior per seller-stories.md:38-39, but it changes
    user-visible behavior. The Validator must review acceptance criteria.
  - Medium: selective git add is error-prone. Must verify `git status --short`
    shows ONLY ad_create.py staged before committing. The PII-consent changes
    are tracked in a separate (future) block.
  - Note: the _get_ad_status helper already exists in the working tree — do NOT
    re-add it. The original plan's implementation sequence step 2 is obsolete.

agents:
  primary: Implementor
  review: Validator
  reason: >
    CRITICAL data-loss fix. The logic is already in the working tree; the risk
    is in the commit hygiene (isolating from PII work) and the new tests. A
    Validator review confirms the cancel-flow contract matches spec intent
    (seller-stories.md:38-39: cancel aborts, does not destroy submitted media).

---

### Block B2 — TX-002: Model-Level File Cleanup Signal

**Finding:** HIGH-001 (HIGH, SPEC-DEVIATION)

**Status:** CONFIRMED not-yet-implemented. `src/backend/apps/media/signals.py`
does not exist. `MediaConfig.ready()` (media/apps.py:13) does not import or
register any signal. `AdImage.Meta` (models.py:607-630) has no signal.

**Source reference:** `.ai/audit/99-validation/07-media-validated-findings.md`
→ "HIGH-001: No physical file cleanup on AdImage cascade-delete"

**Precedent confirmed:** `moderation/signals.py:56-77` uses
`@receiver(post_save, sender=Ad)` + `transaction.on_commit(_deliver)` pattern.

```yaml
id: b2_adimage_signal
title: Add pre_delete signal on AdImage with transaction.on_commit() for TX-then-FS file cleanup
priority: high
depends_on: []
source_reference: .ai/plans/20-media-findings-fix.md
source_section: Block B2 — TX-002: Model-Level File Cleanup Signal

description: >
  AdImage has on_delete=CASCADE but defines no delete() override and no
  pre_delete/post_delete signal. When an Ad is hard-deleted via ORM cascade,
  Django removes the AdImage DB rows at SQL level, but physical files (original
  + 3 thumbnails) are not cleaned up. All 6 sweep commands manually collect
  storage_keys() before the transaction and delete files after commit
  (TX-then-FS pattern), but there is no model-level safety net.

  The established precedent in moderation/signals.py uses post_save +
  transaction.on_commit(). This block uses pre_delete + transaction.on_commit()
  for the same TX-then-FS discipline (Gate R-003, §6).

goals:
  - add a pre_delete signal handler on AdImage that collects storage_keys()
  - register a transaction.on_commit() callback to call delete_photo() for each key
  - preserve the TX-then-FS pattern (files deleted AFTER commit, not inside)
  - avoid conflict with sweep commands (delete_photo handles FileNotFoundError)
  - no DB migration required (signal registration only)

files:
  - path: src/backend/apps/ads/models.py
    targets:
      - type: class
        name: AdImage              # signal target (sender)
  - path: src/backend/apps/media/signals.py    # NEW — signal handler
    targets:
      - type: function
        name: delete_adimage_files_on_delete
  - path: src/backend/apps/media/apps.py
    targets:
      - type: class
        name: MediaConfig          # register signal in ready()

changes:
  - action: add_code
    description: >
      Create src/backend/apps/media/signals.py with a pre_delete receiver on
      AdImage. The handler collects instance.storage_keys() inside the signal
      (which fires within the transaction) and defers file deletion via
      transaction.on_commit(), matching moderation/signals.py's
      deliver_immediate_alerts_on_publish pattern (lines 56-77).

      code_hint: |
        import logging
        from django.db import transaction
        from django.db.models.signals import pre_delete
        from django.dispatch import receiver

        from apps.media.services.filesystem import delete_photo

        logger = logging.getLogger(__name__)


        @receiver(pre_delete, sender=AdImage)
        def delete_adimage_files_on_delete(sender, instance, **kwargs):
            keys = list(instance.storage_keys())
            def _cleanup():
                for key in keys:
                    delete_photo(key)
            transaction.on_commit(_cleanup)

  - action: add_code
    description: >
      In MediaConfig.ready(), add `import apps.media.signals` (noqa: F401)
      after the existing MAX_IMAGE_PIXELS setup so the signal module is loaded
      once at app initialization.

      code_hint: |
        def ready(self) -> None:
            ...  # existing MAX_IMAGE_PIXELS setup
            import apps.media.signals  # noqa: F401 — registers pre_delete

acceptance_criteria:
  - pre_delete signal registered on AdImage via MediaConfig.ready()
  - signal collects storage_keys() and schedules delete_photo() via on_commit
  - file deletion happens AFTER transaction commit (not inside transaction.atomic)
  - double-deletion is safe (delete_photo handles FileNotFoundError gracefully)
  - no DB migration required
  - existing sweep command tests still pass (no behavior change for explicit sweeps)
  - signal fires for AdImage.objects.filter(...).delete() (bulk delete path)

required_tests:
  - test: hard-delete an Ad via ORM cascade (ad.delete()) → assert physical files
    (original + thumbnails) are deleted after commit
    file: src/backend/apps/core/tests/test_sweep_commands.py
  - test: delete_photo failure (e.g. permission error) does NOT roll back the DB cascade
    file: src/backend/apps/core/tests/test_sweep_commands.py
  - test: signal fires for AdImage.objects.filter(...).delete() (bulk delete path)
    file: src/backend/apps/core/tests/test_sweep_commands.py

implementation_sequence:
  1. Create src/backend/apps/media/signals.py with pre_delete handler using on_commit
  2. Register signal import in MediaConfig.ready() in media/apps.py
  3. Add test: ORM cascade delete → physical files cleaned up
  4. Add test: file deletion failure does not block DB cascade
  5. Add test: bulk delete path triggers signal
  6. Run full test_sweep_commands.py suite (no regressions)

architectural_constraints:
  - Must use transaction.on_commit() — the project's TX-then-FS pattern requires
    file deletion AFTER commit. A naive post_delete signal calling delete_photo()
    directly inside the transaction would create the anti-pattern the project
    avoids.
  - Must use storage_keys() — consistent with all 6 sweep commands +
    soft_delete_user_ads.
  - delete_photo() already handles FileNotFoundError (filesystem.py:153-155),
    so double-deletion with sweep commands is safe.
  - Follow the precedent set by moderation/signals.py:56-77 (post_save + on_commit).
  - pre_delete is preferred over post_delete: pre_delete fires before the row is
    removed, guaranteeing instance fields are populated (both work in Django 5.x,
    but pre_delete is the conventional choice for key collection).

risks:
  - Low: signal fires on every AdImage deletion. The on_commit callback is
    deferred and safe, but adds a small per-delete overhead. Negligible at
    current scale.
  - Low: signal + sweep command double-deletion is safe (FileNotFoundError
    terminal case), but worth documenting for future maintainers.

agents:
  primary: Implementor
  review: Validator
  reason: >
    The HIGH-001 fix approach (pre_delete + on_commit) is confirmed correct by
    the auditor's verification and has a direct precedent in
    moderation/signals.py:56-77. No Researcher gate is needed — the
    transaction.on_commit() pattern is already established. A Validator review
    confirms the signal registration location (media/apps.py) and TX-then-FS
    compliance.

---

### Block B3 — TX-003: Staging Directory for In-Flight Uploads

**Finding:** HIGH-002 (HIGH, SPEC-DEVIATION)

**Status:** CONFIRMED not-yet-implemented. `save_photo` (ad_create.py:1020-1064)
writes flat to `os.path.join(settings.MEDIA_ROOT, key)` — no staging/ subdir.
`submit_ad` (submission.py:137-155) reads from `MEDIA_ROOT` directly — no move.
`_walk_media_files` (sweep_orphaned_media.py:46-60) has no staging/ exclusion.

**Source reference:** `.ai/audit/99-validation/07-media-validated-findings.md`
→ "HIGH-002: Orphan sweep deletes in-flight uploads"

```yaml
id: b3_staging_directory
title: Implement staging directory for in-flight uploads to protect against orphan sweep race
priority: high
depends_on:
  - b1_cancel_flow_fix    # B1 must be committed first; save_photo is in the same file
source_reference: .ai/plans/20-media-findings-fix.md
source_section: Block B3 — TX-003: Staging Directory for In-Flight Uploads
research_status: REQUIRED  # Gate R-001 (§6)

description: >
  The orphan sweep (sweep_orphaned_media) collects referenced keys exclusively
  from AdImage rows and walks the entire MEDIA_ROOT (excluding only seed/).
  However, save_photo() writes uploaded photos to MEDIA_ROOT flat
  (os.path.join(settings.MEDIA_ROOT, key)) and stores the key in FSM state
  BEFORE submit_ad() creates AdImage rows (minutes later). If the hourly sweep
  runs mid-upload, in-flight files are classified as orphans and deleted.
  The findings recommend a staging subdirectory excluded from the sweep, with
  files moved to permanent storage on successful submit_ad.

  Line numbers in the original plan drift ~5-10 lines from the current codebase
  (audit was Sep-12; code reviewed Sep-15). All references below use semantic
  anchors.

goals:
  - accept uploads into a staging/ subdirectory of MEDIA_ROOT
  - exclude staging/ from _walk_media_files (mirror the existing seed/ exclusion)
  - move files from staging/ to permanent storage on successful submit_ad
  - ensure delete_photo works for staging keys (path-contained check already
    allows staging/<key> subpaths via KEY_FORMAT_REGEX)
  - no change to thumbnail generation or media_gate serving

research_questions:
  - >
    STAGING-001: Where exactly should the staging→permanent move occur relative
    to the transaction.atomic() block in submit_ad? → RESOLVED (§6 Gate R-001):
    Move BEFORE the TX, in the pre-TX block (submission.py:135-155), alongside
    thumbnail generation. Mirrors the project's TX-then-FS pattern documented at
    submission.py:135-136.
  - >
    STAGING-002: Does save_photo() write to staging/ and return a staging key,
    or should a wrapper add the staging prefix? → RESOLVED (§6 Gate R-001):
    save_photo writes to staging/ and returns the staging key. The collision-
    retry loop at ad_create.py:1064 must also prepend the staging prefix (caveat
    flagged in §6).
  - >
    STAGING-003: Does the staging key format (staging/<uuid>.jpg) comply with
    KEY_FORMAT_REGEX? → RESOLVED (§6 Gate R-001): YES. The actual regex at
    filesystem.py:28-31 has TWO leading [A-Za-z0-9] chars (not one as quoted
    in the original plan), but staging/ starts with "st" (both alphanumeric),
    so it matches. assert_storage_key_contained() also passes. Verified with
    Python re.match.
  - >
    STAGING-004: Are thumbnails for in-flight uploads ever served before
    submission? → RESOLVED (§6 Gate R-001): NO. Thumbnails are generated only
    in submit_ad (submission.py:137-155), pre-TX. media_gate only serves keys
    referenced by AdImage rows for PUBLISHED ads. Staging files are never served.
  - >
    STAGING-005: Interaction with B2 (AdImage pre_delete signal)? → RESOLVED
    (§6 Gate R-001): NO conflict. After the move, AdImage stores permanent keys;
    the signal deletes permanent files, not staging files. On submit_ad rollback,
    no AdImage rows are created, so the signal never fires.
  - >
    STAGING-006: os.replace (atomic rename) vs shutil.move (cross-filesystem)?
    → RESOLVED (§6 Gate R-001): os.replace with shutil.move fallback (OSError
    EXDEV). staging/ shares the same Docker volume as permanent MEDIA_ROOT → same
    filesystem → os.replace is atomic. Consistent with existing os.open(O_CREAT|
    O_EXCL) patterns in save_photo and ThumbnailService.
  - >
    STAGING-007: What happens to abandoned staging files (user abandons mid-flow)?
    → RESOLVED (§6 Gate R-001): Gap confirmed — staging/ is excluded from the
    orphan sweep, so abandoned files persist indefinitely. cmd_cancel deletes
    FSM-state staging keys, but only if the user sends /cancel. Draft sweep
    (30-min TTL) collects keys from AdImage rows, but DRAFT ads have none.
    **Fix:** add a TTL-based reclamation in the orphan sweep (delete staging
    files older than 2 hours).

files:
  - path: src/telegram_bot/handlers/ad_create.py
    targets:
      - type: function
        name: save_photo           # write to staging/ subdir
      - type: function
        name: process_photos       # FSM stores staging key
  - path: src/backend/apps/ads/services/submission.py
    targets:
      - type: function
        name: submit_ad            # move staging/<key> → <key> before TX
      - type: function
        name: AdImageService.create_or_skip  # receives permanent key
  - path: src/backend/apps/media/management/commands/sweep_orphaned_media.py
    targets:
      - type: function
        name: _walk_media_files    # add staging/ exclusion
      - type: constant
        name: _SEED_SUBDIR         # add _STAGING_SUBDIR constant alongside
  - path: src/backend/apps/media/services/filesystem.py
    targets:
      - type: function
        name: delete_photo         # NO CHANGE (path-agnostic, handles staging/<key>)
      - type: function
        name: assert_storage_key_contained  # NO CHANGE
      - type: constant
        name: KEY_FORMAT_REGEX     # NO CHANGE (allows staging/ subpaths; verified YES)
      - type: constant
        name: STAGING_SUBDIR       # NEW — shared constant "staging"
      - type: constant
        name: STAGING_PREFIX       # NEW — shared constant "staging/" (exported from __init__.py)

changes:
  - action: add_code
    description: >
      Add `_STAGING_SUBDIR = "staging"` constant in sweep_orphaned_media.py,
      mirroring the existing `_SEED_SUBDIR = "seed"` pattern.
  - action: modify
    description: >
      In _walk_media_files, add a staging/ exclusion condition alongside the
      existing seed/ exclusion.
  - action: modify
    description: >
      In save_photo (ad_create.py), write to
      os.path.join(settings.MEDIA_ROOT, "staging", key) and return the staging
      key (staging/<key>). os.makedirs already handles directory creation.
      IMPORTANT: the collision-retry at line 1064 calls generate_storage_key()
      which returns a bare <uuid>.jpg — the staging prefix must be re-applied
      in the retry loop to avoid writing to permanent on collision.
  - action: add_code
    description: >
      In submit_ad (submission.py), move files from staging/<key> to <key>
      (permanent MEDIA_ROOT) BEFORE the transaction.atomic() block (after
      thumbnail generation, before line 158). Move ALL key fields (original +
      all 3 thumbnails), stripping the staging/ prefix. Use os.replace with
      shutil.move fallback for cross-filesystem safety. Conditional on
      key.startswith(STAGING_PREFIX) so test fixtures that bypass save_photo
      (e.g. test_save_photo_integration.py:81 "photo.jpg") are unaffected.
  - action: add_code
    description: >
      Add STAGING_PREFIX import to submission.py; add a _move_staging_to_permanent
      helper (or inline batch move) that iterates all key fields per photo,
      strips the staging/ prefix, and os.replace's each file.
  - action: modify
    description: >
      In process_photos (ad_create.py), the stored storage_key is now a staging
      key (staging/<key>). submit_ad moves it to permanent before AdImage creation
      — no change needed in process_photos itself (it just stores what save_photo
      returns).
  - action: add_code
    description: >
      In sweep_orphaned_media.py, add STAGING_TTL_SECONDS constant
      (2 * 60 * 60 = 2 hours) and a _reclaim_stale_staging() helper that deletes
      staging/ files older than the TTL. Call it in handle() after the main
      orphan sweep. This resolves STAGING-007 (abandoned staging files).

acceptance_criteria:
  - uploads written to staging/ subdirectory, not flat in MEDIA_ROOT
  - staging/ excluded from orphan sweep (_walk_media_files)
  - on successful submit_ad, staging files (original + thumbnails) are moved to permanent
  - AdImage rows reference permanent keys (not staging keys)
  - delete_photo works for both staging and permanent keys (no change needed)
  - media_gate serving unaffected (staging files never served)
  - in-flight staging upload survives an orphan sweep (regression test)
  - abandoned staging files older than 2h TTL are reclaimed by the sweep

required_tests:
  - test: save_photo writes to staging/ subdir
    file: src/backend/apps/media/tests/test_save_photo_exif.py (existing — verify path)
    class: TestSavePhotoExifStripping
  - test: in-flight staging upload survives sweep_orphaned_media
    file: src/backend/apps/media/tests/test_sweep_orphaned_media.py
  - test: stale staging file (old mtime) reclaimed by sweep; fresh file preserved
    file: src/backend/apps/media/tests/test_sweep_orphaned_media.py
  - test: successful submit_ad moves file from staging/ to permanent MEDIA_ROOT
    file: src/telegram_bot/tests/test_save_photo_integration.py
  - test: rollback in submit_ad leaves permanent files (swept as orphans)
    file: src/backend/apps/ads/services/tests/ or src/backend/apps/ads/tests/
  - test: cmd_cancel deletes staging key from FSM state
    file: src/telegram_bot/tests/test_ad_create.py
    class: TestCancelAfterSubmit (B1 regression — verify staging keys)

implementation_sequence:
  1. [COMPLETED] Researcher gate — Gate R-001 (§6) resolved: staging dir approved,
     move before TX, os.replace + fallback, staging TTL for abandoned files
  2. Add STAGING_SUBDIR/STAGING_PREFIX constants to filesystem.py + export
  3. Add _STAGING_SUBDIR + _STAGING_TTL_SECONDS to sweep_orphaned_media.py
  4. Modify _walk_media_files to exclude staging/ (mirror seed/ pattern)
  5. Modify save_photo to write to staging/ subdir, return staging key
     (collision-retry must also prepend staging prefix)
  6. Modify submit_ad to move staging→permanent for ALL key fields before TX;
     strip staging/ prefix from photo dict keys
  7. Add _reclaim_stale_staging() to sweep command handle()
  8. Add/update tests: staging survival, TTL reclamation, submit_ad move, rollback
  9. Run: test_sweep_orphaned_media.py + test_save_photo_integration.py
     + test_thumbnail_integration.py + test_ad_create.py

architectural_constraints:
  - Must preserve TX-then-FS: file move happens BEFORE transaction.atomic() in
    submit_ad (filesystem I/O outside the TX so a DB rollback doesn't leave
    FS/DB desynced). Mirrors the existing thumbnail-generation pre-TX pattern
    (submission.py:137-155).
  - staging/ key format must comply with KEY_FORMAT_REGEX (verified: YES).
  - delete_photo() and assert_storage_key_contained() work unchanged for
    staging/<key> paths (verified: YES).
  - No new state to manage (unlike a "pending uploads registry" model/cache-set
    approach which adds a new table or cache key lifecycle).
  - B1 must be committed before B3 edits save_photo (same file).

risks:
  - Medium-High: multi-file change to the core upload path. A bug in the
     staging→permanent move could cause 100% upload failure. Requires thorough
     integration tests covering success, rollback, and concurrent sweep.
  - Medium: if the staging→permanent move fails (e.g. cross-filesystem rename),
     os.replace raises. Mitigated with shutil.move fallback (STAGING-006 resolved).
  - Medium (RESOLVED): staging files that never reach submit_ad (user abandons
     mid-flow) are excluded from the orphan sweep. Mitigated by STAGING_TTL
     reclamation (2-hour TTL in orphan sweep) + cmd_cancel deletes FSM-state keys.
  - Low: collision-retry in save_photo (ad_create.py:1064) must re-apply staging
     prefix; naively prepending only at the write path writes to permanent on
     collision. Fixed per §6 STAGING-002 guidance.
  - Low: interaction with B2 (HIGH-001 signal). No conflict (see STAGING-005).
  - Low: ThumbnailService propagates the staging/ prefix to thumbnail keys
     (staging/<uuid>-small.jpg etc.); the move in submit_ad must handle ALL key
     fields, not just the original (STAGING-001 guidance).

agents:
  primary: Implementor       # Researcher gate (§6 Gate R-001) COMPLETED; proceed to implement
  supporting:
    - Validator       # review staging→permanent move semantics + sweep exclusion + TTL policy
  reason: >
    HIGH-002 touches the core upload path (save_photo, submission.py,
    sweep_orphaned_media) across 3 modules with multi-file scope. The Researcher
    gate (§6 Gate R-001) has resolved all seven technical uncertainties (STAGING-001
    through STAGING-007) with concrete code evidence. The Implementor may now proceed
    per the implementation_sequence, with Validator review on the move semantics and
    staging TTL policy.

---

### Block B4 — TX-004: Size Pre-Check Before Download

**Finding:** MED-002 (MEDIUM, BEST-PRACTICE)

**Status:** CONFIRMED not-yet-implemented. `process_photos` (ad_create.py:640-731)
calls `download_photo(photo.file_id, message.bot)` at line 697 before
`validate_photo()` at line 706. No `file_size` pre-check exists.

**Source reference:** `.ai/audit/99-validation/07-media-validated-findings.md`
→ "MED-002: Telegram photo downloaded before size validation"

```yaml
id: b4_file_size_precheck
title: Check Telegram PhotoSize.file_size before downloading to prevent memory exhaustion
priority: medium
depends_on: []
source_reference: .ai/plans/20-media-findings-fix.md
source_section: Block B4 — TX-004: Size Pre-Check Before Download

description: >
  The process_photos handler (PHOTOS FSM step) downloads the full photo bytes
  via download_photo() before calling validate_photo(), which checks the 2MB
  size limit (filesystem.py:99). Telegram's PhotoSize object reports file_size
  (Optional[int]), which is available but never checked before download.
  A malicious or buggy client can send arbitrarily large files, consuming bot
  memory and bandwidth before the post-download size check rejects it.

goals:
  - check photo.file_size against the 2MB limit before calling download_photo()
  - if file_size exceeds the limit, reject immediately without downloading
  - if file_size is None (Telegram occasionally omits it), fall through to
    download + validate (keep the post-download validate_photo as defense-in-depth)
  - do NOT remove the post-download validate_photo size check (file_size is
    Telegram-reported, not a security boundary)

files:
  - path: src/telegram_bot/handlers/ad_create.py
    targets:
      - type: function
        name: process_photos      # photo.file_id download at ~line 697

changes:
  - action: add_code
    description: >
      Before download_photo(photo.file_id, message.bot), check
      photo.file_size against MAX_PHOTO_SIZE_BYTES (2 * 1024 * 1024). If
      exceeded, answer and return. If None, fall through to download +
      validate_photo. Import MAX_PHOTO_SIZE_BYTES from filesystem.py if it
      exists, or define as a module constant.
    code_hint: |
      MAX_PHOTO_BYTES = 2 * 1024 * 1024
      if photo.file_size is not None and photo.file_size > MAX_PHOTO_BYTES:
          await message.answer("Photo too large. Maximum size is approximately 2MB.")
          return

acceptance_criteria:
  - photo.file_size > 2MB → download_photo NOT called, user gets error message
  - photo.file_size is None → falls through to download + validate_photo
  - photo.file_size <= 2MB → proceeds to download + validate_photo
  - post-download validate_photo size check remains (defense-in-depth)

required_tests:
  - test: PhotoSize with file_size > 2MB → download_photo not called (mock spy)
    file: src/telegram_bot/tests/test_ad_create.py
    class: TestProcessPhotos
  - test: PhotoSize with file_size = None → falls through to download + validate
    file: src/telegram_bot/tests/test_ad_create.py
  - test: PhotoSize with file_size <= 2MB → proceeds normally
    file: src/telegram_bot/tests/test_ad_create.py

implementation_sequence:
  1. Add MAX_PHOTO_BYTES constant (2 * 1024 * 1024) near the top of the module
    or import from filesystem.py
  2. Insert file_size pre-check before download_photo in process_photos
  3. Add 3 test cases (oversize rejected, None falls through, valid proceeds)
  4. Run TestProcessPhotos suite

risks:
  - Low: file_size is Optional[int] — must handle None gracefully (fall through).
    Verified: aiogram 3.x PhotoSize.file_size is Optional[int].
  - Low: file_size is Telegram-reported, not security-trusted — the post-download
    validate_photo check must remain. Documented in acceptance criteria.

agents:
  primary: Implementor
  reason: >
    3-line pre-check using a well-documented aiogram 3.x API attribute. No
    architectural uncertainty. The None-handling and defense-in-depth pattern
    are explicitly documented in the finding.

---

### Block B5 — TX-005: DB Indexes on AdImage Lookup Fields

**Finding:** MED-003 (MEDIUM, BEST-PRACTICE)

**Status:** CONFIRMED not-yet-implemented. `AdImage.Meta` (models.py:607-630)
has NO `indexes` list — only `db_table`, `ordering`, and `constraints`. The
only indexed field is `sha256` (with `db_index=True` at line 601). The
`media_gate` view queries with OR conditions across `image`,
`thumbnail_small`, `thumbnail_medium`, `thumbnail_large` (listings.py:169-177).

**Source reference:** `.ai/audit/99-validation/07-media-validated-findings.md`
→ "MED-003: No DB indexes on AdImage lookup fields"

**Advisory (§0.7):** `db-indexes.md:35-39` documents `IX_ads_pub_condition`
(partial index on `listing_condition_id` for PUBLISHED) which does **not**
exist in `Ad.Meta.indexes`. This is out of scope for B5 (different model).
Doc-specialist should note but NOT fix.

```yaml
id: b5_adimage_indexes
title: Add DB indexes on AdImage image and thumbnail_* lookup fields + migration
priority: medium
depends_on: []
source_reference: .ai/plans/20-media-findings-fix.md
source_section: Block B5 — TX-005: DB Indexes on AdImage Lookup Fields

description: >
  AdImage.Meta defines only CheckConstraint entries and db_index=True on sha256.
  The media_gate view queries with OR conditions across image, thumbnail_small,
  thumbnail_medium, thumbnail_large on every image request (listings.py:169-177),
  then a second query for the published-check (listings.py:190). Without indexes
  on these fields, every image request triggers sequential scans on ad_images.
  db-indexes.md:266-269 only documents IX_adimages_sha256.

goals:
  - add models.Index entries to AdImage.Meta.indexes for image, thumbnail_small,
    thumbnail_medium, thumbnail_large
  - generate and review the migration
  - update db-indexes.md to document the new indexes
  - verify query correctness unchanged
  - NOTE advisory: IX_ads_pub_condition documented in db-indexes.md but missing
    from Ad.Meta.indexes — out of scope, do NOT add

files:
  - path: src/backend/apps/ads/models.py
    targets:
      - type: class
        name: AdImage
      - type: class
        name: AdImage.Meta       # add indexes list (currently absent)
  - path: src/backend/apps/ads/migrations/     # NEW migration (auto-generated)
  - path: docs/02-database/db-indexes.md      # document new indexes

changes:
  - action: add_code
    description: >
      Add an `indexes` list to AdImage.Meta with B-tree indexes on image,
      thumbnail_small, thumbnail_medium, thumbnail_large.
    code_hint: |
      class Meta:
          db_table = "ad_images"
          ordering = ["position"]
          constraints = [...]
          indexes = [
              models.Index(name="IX_adimages_image", fields=["image"]),
              models.Index(name="IX_adimages_thumb_small", fields=["thumbnail_small"]),
              models.Index(name="IX_adimages_thumb_medium", fields=["thumbnail_medium"]),
              models.Index(name="IX_adimages_thumb_large", fields=["thumbnail_large"]),
          ]

acceptance_criteria:
  - AdImage.Meta.indexes contains 4 B-tree indexes (image + 3 thumbnails)
  - migration generated and reviewed (additive, backward-compatible)
  - db-indexes.md:266-269 updated with the 4 new index entries
  - test_media_security.py (TestMediaGateThumbnailResolution) still passes
    (query correctness unchanged)
  - migration applies cleanly (--create-db test run)
  - advisory noted but IX_ads_pub_condition NOT added (different model, out of scope)

required_tests:
  - test: migration applies (schema migration test)
  - test: TestMediaGateThumbnailResolution tests still pass (query correctness)
    file: src/backend/apps/ads/tests/test_media_security.py
  - test: OR-query across 4 fields uses index (verify EXPLAIN shows index scan)
    file: src/backend/apps/ads/tests/test_media_security.py

implementation_sequence:
  1. Add indexes list to AdImage.Meta in models.py
  2. Run `python manage.py makemigrations ads` to generate the migration
  3. Review the generated migration (additive AddIndex operations)
  4. Update db-indexes.md with the 4 new index entries
  5. Run --create-db test invocation
  6. Run test_media_security.py (TestMediaGateThumbnailResolution + TestMediaAccessControl)

architectural_constraints:
  - Indexes are additive (backward-compatible) — safe for rolling deploy.
  - Django auto-generates AddIndex migrations. Document the lock-on-large-table
    consideration; current table size is small (development dataset).
  - PostgreSQL can use bitmap scans across multiple B-tree indexes for OR
    conditions — the 4 separate indexes support the media_gate OR query pattern.
  - IX_ads_pub_condition advisory: out of scope — do NOT attempt to add this
    index to Ad.Meta (belongs to a different model/spec).

risks:
  - Low: index bloat on write-heavy workloads. Current write volume (bot uploads)
    is low. Negligible.
  - Low: migration lock on large table. Document and schedule during low-traffic
    window. Current ad_images table is small.

agents:
  primary: Implementor
  supporting: Doc-specialist
  reason: >
    Additive, backward-compatible migration. The index names and fields follow
    the existing db-indexes.md naming convention (IX_adimages_*). A
    Doc-specialist updates db-indexes.md to keep the spec in sync (project rule
    #14). The IX_ads_pub_condition advisory discrepancy is noted for the
    Doc-specialist but is NOT in scope for this block.

---

### Block B6 — TX-006: Complete EXIF/Metadata Strip

**Finding:** LOW-001 (LOW, BEST-PRACTICE)

**Status:** CONFIRMED not-yet-implemented. `strip_photo_exif`
(filesystem.py:193-211) calls `ImageOps.exif_transpose(img)` which copies the
original's info dict (including icc_profile), then `img.info.pop("exif", None)`
at line 208 — removing only the EXIF segment. No `icc_profile` pop exists.

**Source reference:** `.ai/audit/99-validation/07-media-validated-findings.md`
→ "LOW-001: Incomplete EXIF/metadata stripping in strip_photo_exif"

```yaml
id: b6_exif_icc
title: Pop icc_profile in strip_photo_exif to complete metadata stripping
priority: low
depends_on: []
source_reference: .ai/plans/20-media-findings-fix.md
source_section: Block B6 — TX-006: Complete EXIF Strip

description: >
  strip_photo_exif (filesystem.py:193-211) calls ImageOps.exif_transpose(img)
  which copies the original's info dict (including icc_profile), then
  img.info.pop("exif", None) — removing only the EXIF segment. On img.save(),
  Pillow writes icc_profile to the output if present in img.info. ICC profiles
  can embed camera manufacturer/model, color calibration data, and serial numbers.
  The existing test (TestExifStripping) checks EXIF Make/Model/GPS removal but
  has no icc_profile assertion.

goals:
  - pop icc_profile from img.info before save (same pattern as exif pop)
  - add test assertion for icc_profile removal in TestExifStripping
  - keep the existing EXIF Make/Model/GPS stripping tests passing

files:
  - path: src/backend/apps/media/services/filesystem.py
    targets:
      - type: function
        name: strip_photo_exif    # line 193-211; pop at line 208
  - path: src/backend/apps/ads/tests/test_media_security.py  # CORRECTED path: ads/tests, not media/tests
    targets:
      - type: class
        name: TestExifStripping  # lines 268-309

changes:
  - action: modify
    description: >
      Add `img.info.pop("icc_profile", None)` after the existing
      `img.info.pop("exif", None)` line in strip_photo_exif.
    code_hint: |
      img.info.pop("exif", None)
      img.info.pop("icc_profile", None)  # add this line

acceptance_criteria:
  - strip_photo_exif removes icc_profile from img.info before save
  - output JPEG has no icc_profile segment
  - existing EXIF Make/Model/GPS stripping tests still pass
  - new test asserts icc_profile is absent from output

required_tests:
  - test: strip_photo_exif on JPEG with embedded ICC profile → assert output
    has no icc_profile (check via PIL Image.info after re-opening)
    file: src/backend/apps/ads/tests/test_media_security.py
    class: TestExifStripping

implementation_sequence:
  1. Add `img.info.pop("icc_profile", None)` after the exif pop in strip_photo_exif
  2. Add test: icc_profile present in input → absent in output (TestExifStripping)
  3. Run TestExifStripping suite

risks:
  - None. Adds one line; pop() with default None is safe if key absent.

agents:
  primary: Implementor
  reason: >
    One-line additive change in a well-understood Pillow code path. The fix
    pattern (info.pop) is identical to the existing exif pop.

---

### Block B7 — TX-007: Align _serve_image with FileResponse

**Finding:** LOW-002 (LOW, DOC-UPDATE)

**Status:** CONFIRMED not-yet-implemented. `_serve_image` (listings.py:100-117)
docstring claims "Uses FileResponse" but the implementation reads the entire file
into memory (f.read() at line 116) and wraps it in HttpResponse (line 117).
`FileResponse` is not imported in listings.py (line 20 import has only
Http404, HttpRequest, HttpResponse, HttpResponseForbidden).

**Source reference:** `.ai/audit/99-validation/07-media-validated-findings.md`
→ "LOW-002: _serve_image docstring claims FileResponse but uses HttpResponse"

```yaml
id: b7_serve_image_fix
title: Replace HttpResponse with FileResponse in _serve_image to match docstring
priority: low
depends_on: []
source_reference: .ai/plans/20-media-findings-fix.md
source_section: Block B7 — TX-007: Align _serve_image with FileResponse

description: >
  _serve_image (listings.py:100-117) docstring claims "Uses FileResponse to
  stream the file from MEDIA_ROOT" but the implementation reads the entire file
  into memory (f.read()) and wraps it in HttpResponse. FileResponse is not
  imported. This is a dev-only fallback (DEBUG=True); production uses
  X-Accel-Redirect. The findings recommend either (a) use FileResponse to stream
  (matching the docstring) or (b) update the docstring to match the code.

goals:
  - align code with the documented intent (streaming via FileResponse)
  - eliminate dev-mode memory pressure from reading whole files into memory
  - keep the return type annotation correct (FileResponse subclasses HttpResponse)

decision: >
  PREFERRED: Option (a) — use FileResponse. Rationale: the docstring documents
  the intended design (streaming); FileResponse is Django's idiomatic file-serving
  class; the change is 2 lines (import + swap) with zero production impact (dev-
  only). Option (b) (doc fix only) is the fallback if the team prefers strictly
  minimal risk with no behavior change.

files:
  - path: src/backend/apps/ads/views/listings.py
    targets:
      - type: function
        name: _serve_image    # lines 100-117; returns HttpResponse(data) at line 117
      - type: import_block
        name: django.http     # add FileResponse to import (line 20)

changes:
  - action: add_code
    description: >
      Add FileResponse to the django.http import at listings.py:20.
    code_hint: |
      from django.http import FileResponse, Http404, HttpRequest, HttpResponse, HttpResponseForbidden
  - action: modify
    description: >
      Replace `data = f.read(); return HttpResponse(data, content_type=...)` with
      `return FileResponse(open(file_path, "rb"), content_type="image/jpeg")`
      to stream the file instead of loading it into memory.
    code_hint: |
      return FileResponse(open(file_path, "rb"), content_type="image/jpeg")

acceptance_criteria:
  - _serve_image returns a FileResponse (streams from disk, does not load whole file into memory)
  - FileResponse is imported at listings.py:20
  - return type annotation `-> HttpResponse` is still correct (FileResponse subclasses HttpResponse)
  - _serve_image still raises Http404 for non-existent files and Http404 for traversal keys
  - Doc-specialist verifies the docstring now accurately describes FileResponse streaming
  - ordering: B7 must ship BEFORE B9 (shared _serve_image edit)

required_tests:
  - test: _serve_image returns FileResponse (streamed, not HttpResponse with full payload)
    file: src/backend/apps/ads/tests/test_media_security.py
    class: TestMediaAccessControl
  - test: existing 404 + traversal-rejection tests still pass
    file: src/backend/apps/ads/tests/test_media_security.py

implementation_sequence:
  1. Add FileResponse to the django.http import
  2. Replace the f.read() + HttpResponse return with FileResponse(open(...))
  3. Verify _serve_image docstring is accurate (it already says FileResponse — no doc change needed)
  4. Add test asserting FileResponse is returned
  5. Run TestMediaAccessControl suite

risks:
  - None (dev-only path; FileResponse is a well-understood Django class).
  - Note: FileResponse takes ownership of the file handle and closes it when
    garbage-collected. Using open() inline is the standard Django pattern.
  - B7 must ship before B9: B9 adds cache-control headers to the response
    returned by _serve_image. Since B9 sets headers on the response object
    (HttpResponse.headers), and FileResponse subclasses HttpResponse, the
    header-setting code works identically. But B9's implementation must target
    the FileResponse return type. Documented as B9 depends_on: b7_serve_image_fix.

agents:
  primary: Implementor
  supporting: Doc-specialist
  reason: >
    2-line change (import + return swap) in a dev-only code path. The Doc-
    specialist verifies the docstring is now accurate (it already claims
    FileResponse, so the code change makes it truthful). Note interaction with
    B3 (HIGH-002 staging): _serve_image resolves keys via MEDIA_ROOT / image_key;
    staging keys (staging/<key>) resolve the same way — no change needed. B7 and
    B9 both edit _serve_image → B7 ships first.

---

### Block B8 — TX-008: Remove Dead Code in _walk_media_files

**Finding:** LOW-003 (LOW, BEST-PRACTICE)

**Status:** CONFIRMED not-yet-implemented. `_walk_media_files`
(sweep_orphaned_media.py:46-60) contains a dead code block at lines 51-53:
`if rel_dir == ".": if _SEED_SUBDIR in os.listdir(media_root): pass`. The
inner block only contains `pass`, performs no action, and does not affect control
flow. The actual seed exclusion is at lines 54-56.

**Source reference:** `.ai/audit/99-validation/07-media-validated-findings.md`
→ "LOW-003: Dead code in _walk_media_files"

```yaml
id: b8_dead_code_removal
title: Remove dead no-op if-block in _walk_media_files
priority: low
depends_on: []
source_reference: .ai/plans/20-media-findings-fix.md
source_section: Block B8 — TX-008: Dead Code in _walk_media_files

description: >
  _walk_media_files (sweep_orphaned_media.py:46-60) contains a dead code block
  at lines 51-53: `if rel_dir == ".": if _SEED_SUBDIR in os.listdir(media_root):
  pass`. The inner block only contains `pass`, performs no action, and does not
  affect control flow. The actual seed exclusion is at lines 54-56. This is an
  incomplete refactoring artifact — confusing for maintainers.

goals:
  - remove the dead `if rel_dir == "."` block (lines 51-53)
  - no behavioral change (the block is a verified no-op)

files:
  - path: src/backend/apps/media/management/commands/sweep_orphaned_media.py
    targets:
      - type: function
        name: _walk_media_files    # lines 46-60; dead block at 51-53

changes:
  - action: delete
    description: >
      Remove the 3-line dead block:
      `if rel_dir == ".":\n  if _SEED_SUBDIR in os.listdir(media_root):\n      pass`
    code_hint: |
      # DELETE these lines:
      if rel_dir == ".":
          if _SEED_SUBDIR in os.listdir(media_root):
              pass  # not in the top-level dir, handled below

acceptance_criteria:
  - dead `if rel_dir == "."` block removed from _walk_media_files
  - seed/ exclusion still works (lines 54-56 intact)
  - top-level files still included in walk output
  - all existing test_sweep_orphaned_media.py tests pass unchanged

required_tests:
  - test: test_orphaned_file_is_deleted (existing) — still passes
    file: src/backend/apps/media/tests/test_sweep_orphaned_media.py
  - test: test_seed_subdir_excluded (existing) — still passes
    file: src/backend/apps/media/tests/test_sweep_orphaned_media.py
  - test: test_dry_run_is_nondestructive (existing) — still passes
    file: src/backend/apps/media/tests/test_sweep_orphaned_media.py

implementation_sequence:
  1. Remove the 3-line dead block from _walk_media_files
  2. Run test_sweep_orphaned_media.py full suite (dry-run + delete + seed preservation)

risks:
  - None. The block is a verified no-op (only contains `pass`). No test gap
    — existing sweep tests cover the seed-exclusion and orphan-deletion behavior.

agents:
  primary: Implementor
  reason: >
    Trivial dead-code removal with zero behavioral risk. Existing
    test_sweep_orphaned_media.py tests (dry-run, seed preservation, orphan
    deletion) provide full regression coverage.

---

### Block B9 — TX-009: Cache-Control Headers on media_gate

**Finding:** LOW-004 (LOW, BEST-PRACTICE)

**Status:** CONFIRMED not-yet-implemented. `media_gate` (listings.py:120-198)
sets no Cache-Control, ETag, or Last-Modified headers on any response path.

**Source reference:** `.ai/audit/99-validation/07-media-validated-findings.md`
→ "LOW-004: No cache-control headers on media_gate"

```yaml
id: b9_cache_control
title: Add Cache-Control headers on media_gate responses (immutable for prod, no-cache for dev)
priority: low
depends_on:
  - b2_adimage_signal    # HIGH-001 ensures prompt file deletion on ad status change
  - b7_serve_image_fix   # B7 changes _serve_image return to FileResponse; B9 must target this
source_reference: .ai/plans/20-media-findings-fix.md
source_section: Block B9 — TX-009: Cache-Control Headers on media_gate

description: >
  media_gate (listings.py:120-198) sets no Cache-Control, ETag, or Last-Modified
  headers on any response path. Staff users see any image regardless of ad status
  (bypasses PUBLISHED check); non-staff users only see images referenced by
  PUBLISHED ads. Image storage keys are UUID v4-based and immutable, making
  them excellent candidates for browser/CDN caching. The verifier notes that
  long max-age is safe only if image files are promptly deleted on ad status
  change (provided by Block B2 / HIGH-001 signal fix).

  IMPORTANT (Auditor correction): B9 depends on BOTH B2 and B7.
  - B2 (HIGH-001): prompt file deletion via pre_delete signal makes long
    max-age=31536000 immutable safe. If B2 has not shipped, use conservative
    max-age=3600 with revalidation.
  - B7 (LOW-002): B7 changes _serve_image to return FileResponse instead of
    HttpResponse. B9 adds cache-control headers to the dev response returned by
    _serve_image — must target the FileResponse return type. B7 must ship first.

goals:
  - set Cache-Control: public, max-age=31536000, immutable on production
    (X-Accel-Redirect) responses
  - set Cache-Control: no-cache on development (_serve_image) responses
  - add Vary: Authorization (staff bypass PUBLISHED check — different response
    depends on auth state)
  - use cache_control decorator on media_gate, set headers inline on dev path

files:
  - path: src/backend/apps/ads/views/listings.py
    targets:
      - type: function
        name: media_gate    # lines 120-198; X-Accel-Redirect at 183-185, 196-198
      - type: function
        name: _serve_image  # lines 100-117; called by media_gate in DEBUG mode (lines 182, 194)

changes:
  - action: add_code
    description: >
      Import cache_control from django.views.decorators.cache.
    code_hint: |
      from django.views.decorators.cache import cache_control
  - action: modify
    description: >
      Apply @cache_control(max_age=31536000, immutable=True, public=True) to
      media_gate for production responses, and add Cache-Control: no-cache to
      the _serve_image dev path. Add Vary: Authorization to all responses
      (staff vs non-staff differs).
    code_hint: |
      @cache_control(max_age=31536000, immutable=True, public=True)
      def media_gate(request: HttpRequest, image_key: str) -> HttpResponse:
          ...
          response["Vary"] = "Authorization"
          # for _serve_image dev path:
          # set Cache-Control: no-cache on the returned FileResponse

acceptance_criteria:
  - production (X-Accel-Redirect) responses include
    Cache-Control: public, max-age=31536000, immutable
  - dev (_serve_image) responses include Cache-Control: no-cache
  - Vary: Authorization header present on all media_gate responses
  - staff vs non-staff responses correctly differ (existing access-control tests pass)
  - no regression in TestMediaAccessControl / TestMediaGateThumbnailResolution
  - B7's FileResponse return type is the target for dev cache headers

required_tests:
  - test: media_gate production response has Cache-Control: max-age=31536000, immutable
    file: src/backend/apps/ads/tests/test_media_security.py
    class: TestMediaAccessControl
  - test: media_gate dev response has Cache-Control: no-cache
    file: src/backend/apps/ads/tests/test_media_security.py
  - test: Vary: Authorization present on responses
    file: src/backend/apps/ads/tests/test_media_security.py
  - test: existing access-control tests (published/draft/staff) still pass
    file: src/backend/apps/ads/tests/test_media_security.py

implementation_sequence:
  1. Import cache_control from django.views.decorators.cache
  2. Apply @cache_control decorator on media_gate
  3. Add Vary: Authorization to all response paths in media_gate
  4. For the _serve_image dev path, set Cache-Control: no-cache on the returned
    FileResponse (accounts for B7's FileResponse swap)
  5. Add test assertions for cache headers
  6. Run TestMediaAccessControl + TestMediaGateThumbnailResolution

architectural_constraints:
  - Cache policy must account for staff vs non-staff: staff can view images of
    non-PUBLISHED ads. Vary: Authorization ensures caches key on auth state.
  - Long max-age (1 year immutable) is safe ONLY when B2 (HIGH-001) ensures
    prompt file deletion on ad status change. If B2 has not shipped, use a
    conservative short max-age (e.g. 3600) with revalidation.
  - The cache-control decorator on a function-based view works with Django's
    cache framework. Ensure it does not interfere with X-Accel-Redirect.
  - B7 must ship before B9: _serve_image returns FileResponse (not HttpResponse)
    after B7. B9's dev-path cache headers must target FileResponse.

risks:
  - Low: if an ad transitions PUBLISHED → REJECTED/DELETED, a cached image could
    be served for up to 1 year. Mitigated by B2's prompt file deletion (the file
    is removed from disk, so the cache miss falls through and the AdImage lookup
    returns 404).
  - Low: Vary: Authorization increases cache key cardinality. Acceptable for
    a classifieds board with predominantly anonymous buyers.
  - Dependency risk: B9 depends on B7's FileResponse change. If B7 is not in
    place, B9's dev-path header logic targets HttpResponse — works identically
    (FileResponse subclasses HttpResponse) but B9 should be tested against the
    B7 code path.

agents:
  primary: Implementor
  review: Validator
  reason: >
    Additive HTTP headers on a public view. The cache policy has a moderation
    visibility nuance (staff bypass) that requires a Validator review. B9's
    dependency on B2 (file-deletion guarantee) and B7 (FileResponse return type)
    is explicit in depends_on.

---

## 6. Research & Decision Gates

### Gate R-001 — HIGH-002 Staging Directory Approach (Block B3)

**Status: RESOLVED — Researcher gate complete. Staging directory approved.**

The staging-directory approach for HIGH-002 touches the core upload path across
3 modules (`ad_create.py:save_photo`, `submission.py:submit_ad`,
`sweep_orphaned_media.py:_walk_media_files`). All seven technical uncertainties
are resolved below with concrete code evidence.

### Research Findings Table (STAGING-001 through STAGING-007)

| # | Question | Verdict | Evidence / Rationale |
|---|---|---|---|
| STAGING-001 | Where does the staging→permanent move occur relative to `transaction.atomic()` in submit_ad? | **BEFORE the TX** — in the pre-TX block (submission.py:135-155), alongside thumbnail generation | submission.py:135-136 explicitly documents the TX-then-FS pattern: "Generate thumbnails BEFORE the DB transaction (filesystem I/O outside tx) so a DB rollback does not leave filesystem and DB desynced." The move is also filesystem I/O and MUST follow the same pre-TX discipline. If the TX rolls back, the permanent files (original + thumbnails) become unreferenced orphans and are reclaimed by the normal orphan sweep. Files are NOT left in staging/ on rollback — they are moved before the TX. |
| STAGING-002 | Does save_photo write to staging/ and return a staging key, or is a wrapper used? | **save_photo writes to staging/ and returns the staging key.** No wrapper. | save_photo signature `async def save_photo(storage_key: str, photo_bytes: bytes) -> str` (ad_create.py:1020). It already constructs the path from `key` and returns `key`. The caller at line 715 `storage_key = await save_photo(generate_storage_key(), photo_bytes)` stores the return value directly in FSM state (lines 719-725). Minimal change: prepend `staging/` to the path and return value. **Caveat:** the collision-retry at line 1064 `key = generate_storage_key()` returns a bare `<uuid>.jpg` (no staging/ prefix) — the staging prefix must be re-applied in the retry loop to avoid writing to permanent on collision. |
| STAGING-003 | Does staging/<key> comply with KEY_FORMAT_REGEX + assert_storage_key_contained? | **YES — verified.** | Actual regex at filesystem.py:28-31 (NOT the plan's quoted one-line-alnum variant — it has TWO leading `[A-Za-z0-9]`):<br>`r"^[A-Za-z0-9][A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*\.jpg$"`<br>`staging/` starts with `st` (both alphanumeric) ✓; `/` separates segments ✓; `<uuid>` starts alphanumeric ✓. All thumbnail variants (`staging/<uuid>-small.jpg` etc.) also match. `assert_storage_key_contained` (filesystem.py:34-65) passes: no NUL, no leading `/`, no `..` in `Path` parts, resolves within MEDIA_ROOT. Verified with Python `re.match` against all expected formats. |
| STAGING-004 | Are staging files ever served via media_gate? | **NO.** | Thumbnails generated only in submit_ad (submission.py:137-155), pre-TX. media_gate (listings.py:120-198) queries `Q(image=key) \| Q(thumbnail_small=key) \| ...` against AdImage rows (line 169-176), then checks `AdStatus.PUBLISHED` (line 190). After staging→permanent move, AdImage stores permanent keys only. Staging files are never referenced by AdImage → never served. No change needed to `_serve_image` or `media_gate`. |
| STAGING-005 | Interaction with B2 (AdImage pre_delete signal)? | **NO conflict.** | B2's signal fires on AdImage pre_delete, calls `delete_photo(instance.storage_keys())`. After the move, AdImage stores permanent keys — signal deletes permanent files, never staging files. If submit_ad rolls back, no AdImage rows are created (inside TX), so the signal never fires. `delete_photo` handles both staging and permanent keys unchanged (filesystem.py:146-150: `os.path.join(MEDIA_ROOT, storage_key)` + `os.remove`). |
| STAGING-006 | os.replace (atomic rename) vs shutil.move (cross-filesystem)? | **os.replace, with shutil.move fallback.** | staging/ is a subdirectory of MEDIA_ROOT; both share the same Docker volume mount → same filesystem → `os.replace` is atomic. Consistent with existing codebase patterns: save_photo uses `os.open(O_CREAT\|O_EXCL)` (ad_create.py:1043), ThumbnailService uses `os.open(O_CREAT\|O_EXCL)` (thumbnails.py:91), both atomic creates. `os.replace` raises `OSError` (errno EXDEV/`Cross-device link`) on cross-FS; a `try: os.replace / except OSError: shutil.move` fallback handles that edge case with negligible overhead (2MB max files). |
| STAGING-007 | What happens to abandoned staging files (user abandons mid-flow)? | **Gap confirmed.** Staging/ excluded from orphan sweep → abandoned files persist forever. Two reclamation paths exist but are incomplete. **Recommendation: add a staging TTL to the orphan sweep.** | `cmd_cancel` (ad_create.py:125-126) deletes FSM-state staging keys via `delete_photo` — works if user sends `/cancel`. `sweep_drafts` (sweep_drafts.py:45) uses 30-min TTL but only collects keys from AdImage rows (line 63-67) — DRAFT ads have NO AdImage rows (created only in submit_ad), so staging files are NOT reclaimed. `soft_delete_user_ads` (deletion.py:197-202) also collects from AdImage rows — same gap. **Fix:** add a TTL-based sweep for staging/ files in the orphan sweep command: delete staging files older than a configurable threshold (recommended: 2 hours, safely beyond the 30-min draft TTL). |

### Key Discrepancy Found

The §5 Block B3 code hint for the move (lines 531-533) is **inconsistent with the
recommended approach** (STAGING-002). The hint treats `photo["storage_key"]` as a
permanent key and prepends `staging/` for the source path:

```python
# PLAN CODE HINT (incorrect — would produce double "staging/" prefix):
staging_path = os.path.join(settings.MEDIA_ROOT, "staging", photo["storage_key"])
permanent_path = os.path.join(settings.MEDIA_ROOT, photo["storage_key"])
```

If `save_photo` returns `staging/<uuid>.jpg` (per STAGING-002), then `photo["storage_key"]`
is already `staging/<uuid>.jpg`, so `staging_path` becomes `MEDIA_ROOT/staging/staging/<uuid>.jpg`
(double prefix — file not found) and `permanent_path` becomes `MEDIA_ROOT/staging/<uuid>.jpg`
(stays in staging — never promoted). The Implementor must instead **strip** the
`staging/` prefix from each key (original + all 3 thumbnails) and move
`MEDIA_ROOT/staging/<key>` → `MEDIA_ROOT/<key>`. See "Implementation Guidance" below.

### Thumbnail Key Propagation (critical for move semantics)

`ThumbnailService.generate_thumbnails` (thumbnails.py:61-76) derives thumbnail keys
from the input `original_key` via `os.path.splitext` + `f"{stem}-{size}.jpg"`. When
called with a staging key (`staging/<uuid>.jpg`), the stem is `staging/<uuid>`, so
thumbnail keys become `staging/<uuid>-small.jpg`, `staging/<uuid>-medium.jpg`,
`staging/<uuid>-large.jpg`. The move in submit_ad must handle ALL key fields, not
just the original `storage_key`.

### Implementation Guidance (for the Implementor)

1. **Add shared constants** in `filesystem.py` (consumed by ad_create.py, submission.py,
   sweep_orphaned_media.py):
   ```python
   STAGING_SUBDIR = "staging"
   STAGING_PREFIX = f"{STAGING_SUBDIR}/"
   ```
   Export from `apps/media/services/__init__.py`.

2. **Modify `save_photo`** (ad_create.py:1020-1064) — write to staging, return staging key:
   ```python
   # Line 1051-1064 (current):
   key = storage_key                       # "<uuid>.jpg"
   while True:
       media_path = os.path.join(settings.MEDIA_ROOT, key)   # MEDIA_ROOT/<uuid>.jpg (FLAT!)
       try:
           await asyncio.to_thread(_write, media_path, photo_bytes)
           return key
       except FileExistsError:
           key = generate_storage_key()    # collision retry — returns bare <uuid>.jpg

   # FIXED (staging-aware, collision-safe):
   key = storage_key                       # "<uuid>.jpg" (base key, no prefix)
   while True:
       staging_key = f"{STAGING_PREFIX}{key}"        # "staging/<uuid>.jpg"
       media_path = os.path.join(settings.MEDIA_ROOT, staging_key)
       try:
           await asyncio.to_thread(_write, media_path, photo_bytes)
           return staging_key             # return staging key to caller
       except FileExistsError:
           key = generate_storage_key()   # regenerate base key; loop re-prepends prefix
   ```
   Import `STAGING_PREFIX` from `apps.media.services.filesystem`.

3. **Modify `submit_ad`** (submission.py) — move staging→permanent BEFORE the TX block
   (after thumbnail generation at line 155, before `transaction.atomic()` at line 158):
   ```python
   # After thumbnail generation loop (post-line 155), before line 158 transaction.atomic():
   _move_staging_to_permanent(input.photos)

   def _move_staging_to_permanent(photos: list[dict]) -> None:
       """Move files from staging/ to permanent MEDIA_ROOT; update keys to permanent."""
       key_fields = ("storage_key", "thumbnail_small", "thumbnail_medium", "thumbnail_large")
       for photo in photos:
           for field in key_fields:
               key = photo.get(field)
               if not key or not key.startswith(STAGING_PREFIX):
                   continue  # already permanent (e.g. seed data, test fixtures)
               permanent_key = key.removeprefix(STAGING_PREFIX)
               staging_path = os.path.join(settings.MEDIA_ROOT, key)
               permanent_path = os.path.join(settings.MEDIA_ROOT, permanent_key)
               if os.path.exists(staging_path):
                   try:
                       os.replace(staging_path, permanent_path)
                   except OSError as exc:
                       if exc.errno == errno.EXDEV:
                           shutil.move(staging_path, permanent_path)
                       else:
                           raise
               photo[field] = permanent_key
   ```
   This is **conditional** (only moves keys with the staging prefix), so tests that
   bypass `save_photo` and write to permanent directly (e.g. test_save_photo_integration.py:81-82
   writes `storage_key = "photo.jpg"`) remain unaffected.

4. **Modify `_walk_media_files`** (sweep_orphaned_media.py:46-60) — exclude staging/
   alongside seed/:
   ```python
   # Add constant alongside _SEED_SUBDIR (line 31):
   _STAGING_SUBDIR = "staging"
   # Add to the exclusion check (after line 55-56):
   if (rel_dir == _STAGING_SUBDIR or rel_dir.startswith(f"{_STAGING_SUBDIR}/")):
       continue
   ```

5. **Add staging TTL reclamation** (STAGING-007) — in the sweep command `handle()`
   (sweep_orphaned_media.py:78-116), after the main orphan sweep (after line 113):
   ```python
   # After the main orphan-deletion loop, reclaim abandoned staging files:
   _reclaim_stale_staging(media_root, _STAGING_TTL_SECONDS)

   _STAGING_TTL_SECONDS = 2 * 60 * 60  # 2 hours (safely beyond 30-min draft TTL)

   def _reclaim_stale_staging(media_root: str, ttl_seconds: int) -> None:
       """Delete staging files older than ttl_seconds (abandoned uploads)."""
       staging_root = os.path.join(media_root, STAGING_SUBDIR)
       if not os.path.isdir(staging_root):
           return
       now = time.time()
       for dirpath, _dirnames, filenames in os.walk(staging_root):
           for name in filenames:
               path = os.path.join(dirpath, name)
               try:
                   if now - os.path.getmtime(path) >= ttl_seconds:
                       os.remove(path)
                       logger.info("Reclaimed stale staging file: %s",
                                   os.path.relpath(path, media_root))
               except OSError:
                   logger.exception("Failed to reclaim staging file: %s", path)
   ```

### Updated Test Recommendations

| Test | File | Notes |
|---|---|---|
| save_photo writes to staging/ subdir | `src/backend/apps/media/tests/test_save_photo_exif.py` or `test_thumbnail_integration.py` | Existing tests use the return value for path — should pass with staging prefix; verify |
| In-flight staging upload survives sweep | `src/backend/apps/media/tests/test_sweep_orphaned_media.py` | New test: create `staging/` file, run sweep, assert file preserved |
| submit_ad moves staging→permanent | `src/telegram_bot/tests/test_save_photo_integration.py` | New test: staging file moved to permanent, AdImage stores permanent key |
| Rollback in submit_ad leaves permanent orphan (swept) | ads services tests | On TX rollback, permanent files exist but unreferenced → orphan sweep deletes them |
| Stale staging file (old mtime) reclaimed | `test_sweep_orphaned_media.py` | New test: create old staging file, run sweep, assert deleted; create fresh staging file, assert preserved |
| cmd_cancel deletes staging file | `src/telegram_bot/tests/test_ad_create.py` | Existing cancel tests must pass with staging keys |

### Impact on Existing Tests

- **test_save_photo_exif.py:80** — calls `save_photo("exif-test.jpg", ...)` and builds path from return value. With staging, returns `staging/exif-test.jpg`; `media_root / storage_key` resolves correctly. `_write` calls `os.makedirs(os.path.dirname(path))` which creates `staging/` subdir. **PASS with no changes.**
- **test_thumbnail_integration.py:70** — calls `save_photo(generate_storage_key(), ...)`; `original_path = media_root / storage_key` resolves to `staging/<uuid>.jpg`. `generate_thumbnails(bytes, storage_key)` derives `staging/<uuid>-small.jpg` etc. Stem assertion `storage_key.rsplit(".", 1)[0]` → `staging/<uuid>`. **PASS with no changes.**
- **test_save_photo_integration.py:81** — bypasses `save_photo`, writes `storage_key = "photo.jpg"` directly. submit_ad's move is conditional (`if key.startswith(STAGING_PREFIX): continue`) — "photo.jpg" doesn't start with `staging/`, so no move attempted. **PASS with no changes.**
- **test_ad_create.py:259-261** — mocks `save_photo` with `return_value="fake_storage_key"`. No staging prefix. submit_ad's conditional move skips it. **PASS with no changes.**

**Preferred path: Staging directory** — reuses the established `seed/` exclusion pattern,
requires no new state (no model table or cache set), provides clean separation of
in-progress vs. committed files, and follows the project's TX-then-FS pattern
(filesystem I/O before `transaction.atomic()`).

**Alternative (rejected):** Pending-uploads registry (model table or cache set) queried
by `_collect_referenced_keys()`. Adds new state lifecycle, a migration, and ongoing
cleanup. Higher complexity for equivalent protection.

**Bundle with MED-002?** NO — ship separately. MED-002 is a trivial, independent
pre-download size check (Block B4) that reduces memory-exhaustion risk immediately.
The staging directory and the size pre-check solve different problems (orphan sweep
race vs. memory exhaustion).

### Gate R-002 — LOW-002 Code Fix vs Doc Fix (Block B7)

**Status: DECIDED — recommend code fix (FileResponse)**

The findings offer two options: (a) use FileResponse to stream (matching the
docstring), or (b) update the docstring to match the current HttpResponse code.

**Recommendation: Option (a) — use FileResponse.**

Rationale:
1. The docstring documents the *intended* design (streaming). Making code match
   the docstring is preferable to downgrading the doc.
2. FileResponse is Django's idiomatic class for serving files (streaming from
   disk with a generator, not full-buffer).
3. `FileResponse` subclasses `HttpResponse` — the `-> HttpResponse` return
   annotation at listings.py:100 stays valid.
4. The change is 2 lines (import + return swap) in a dev-only path (DEBUG=True).
   Zero production impact.
5. No interaction with HIGH-002 staging: `_serve_image` resolves keys via
   `MEDIA_ROOT / image_key`, and staging keys (`staging/<key>`) resolve the same
   way.
6. B7 must ship before B9 (both edit `_serve_image`).

No Researcher gate needed — FileResponse is a well-understood Django pattern
with no technical uncertainty. Doc-specialist verifies the docstring is now
accurate (it already claims FileResponse).

### Gate R-003 — HIGH-001 pre_delete vs post_delete Signal (Block B2)

**Status: DECIDED — use pre_delete + transaction.on_commit()**

The findings note that a `post_delete` signal on AdImage would fire inside the
transaction for individual `DELETE` calls. The project's established TX-then-FS
pattern deletes files after `transaction.atomic()` commits.

**Recommendation: pre_delete signal collecting `storage_keys()`, then
`transaction.on_commit()` to call `delete_photo()` for each key.**

Rationale:
1. `pre_delete` fires within the transaction (before the DB row is deleted), so
   `instance.storage_keys()` is still available (all fields are populated).
2. `transaction.on_commit()` ensures files are deleted AFTER the DB transaction
   commits — preserving the TX-then-FS pattern.
3. **Precedent exists:** `moderation/signals.py:56-77` uses exactly this pattern
   (`transaction.on_commit(_deliver)` in a `post_save` signal).
4. The Auditor confirmed this is the correct approach.

No Researcher gate needed — the pattern is established and the Auditor
confirmed it.

---

## 7. Verification Strategy

### Test infrastructure
- Test DB: `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db`
- Fast gate: `$dc run --rm --env PYTEST_SKIP_MARKERS=seed test`
- Single test: `$dc run --rm -e PYTEST_OPTS="-k test_name" test`  # PYTEST_OPTS, never --override-ini=addopts=
- Fresh schema (after B5 migration): `$dc run --rm --env PYTEST_OPTS="--create-db -n auto" test`
- Lint: `uv run ruff check <path>` · Auto-fix: `uv run ruff check --fix <path>`
- i18n: new user-visible strings (if any) must pass `test_i18n_completeness.py`

### Per-block test coverage (corrected file paths)

| Block | Test file | New tests required |
|---|---|---|
| B1 | `src/telegram_bot/tests/test_ad_create.py` | cancel-after-submit preserves files+DB; delete_draft uses storage_keys() |
| B2 | `src/backend/apps/core/tests/test_sweep_commands.py` | ORM cascade → physical files deleted after commit; file-deletion failure doesn't block cascade; bulk delete triggers signal |
| B3 | `test_sweep_orphaned_media.py`, `test_ad_create.py`, ads services tests | staging upload survives sweep; submit_ad moves staging→permanent; rollback leaves staging file |
| B4 | `src/telegram_bot/tests/test_ad_create.py` | oversize file_size → no download; None → falls through; valid → proceeds |
| B5 | `src/backend/apps/ads/tests/test_media_security.py`, migration test | migration applies; OR-query uses index; thumbnail resolution tests pass |
| B6 | `src/backend/apps/ads/tests/test_media_security.py` | icc_profile present in → absent in output (TestExifStripping) |
| B7 | `src/backend/apps/ads/tests/test_media_security.py` | _serve_image returns FileResponse; existing 404 + traversal tests pass |
| B8 | `src/backend/apps/media/tests/test_sweep_orphaned_media.py` | existing tests pass unchanged (no new test needed) |
| B9 | `src/backend/apps/ads/tests/test_media_security.py` | Cache-Control + Vary headers on responses |

### Regression surface

- B1 touches the bot cancel flow → run full `test_ad_create.py` suite.
- B2 touches AdImage deletion → run all sweep command tests
  (`test_sweep_commands.py`) + `test_sweep_orphaned_media.py`.
- B3 touches the upload path → run `test_ad_create.py` +
  `test_sweep_orphaned_media.py` + ads services tests.
- B5 adds a migration → run `--create-db` test invocation; all media tests.
- B7 changes `_serve_image` return type → run all
  `test_media_security.py` (TestMediaAccessControl, TestMediaGateThumbnailResolution).
- B9 adds cache headers → run all `test_media_security.py`.

### i18n consideration

Blocks B1, B4 introduce new user-facing messages (error messages to bot users).
These must be wrapped in `gettext()` and verified via `test_i18n_completeness.py`
if they follow the bot i18n pattern. Review against AGENTS.md rule #16.

---

## 8. Rollout Safety Summary

| Block | Backward-compatible? | Rollout risk | Notes |
|---|---|---|---|
| B1 | No (behavior change: cancel no longer destroys submitted media) | High | CRITICAL data-loss fix; already in working tree; commit + tests + validate |
| B2 | Yes (additive signal) | Low | Must use on_commit for TX-then-FS |
| B3 | No (upload flow change: staging dir) | Medium-High | Requires Researcher gate; multi-file; B1 must commit first (same file) |
| B4 | Yes (additive pre-check) | Low | file_size=None handled gracefully |
| B5 | Yes (additive indexes) | Low | Migration is CREATE INDEX; safe on small table; IX_ads_pub_condition advisory out of scope |
| B6 | Yes (additive pop) | None | One line; Pillow info.pop with default |
| B7 | Yes (FileResponse subclasses HttpResponse) | None | Dev-only path (DEBUG=True); ships before B9 |
| B8 | Yes (dead code removal) | None | Verified no-op |
| B9 | Yes (additive headers) | Low | Depends on B2 (file-deletion guarantee) + B7 (FileResponse return type) |

### Cross-block safety notes

1. **HIGH-001 + HIGH-002 double-deletion safety:** Both the model-level signal
   (B2) and the orphan sweep (B3) call `delete_photo()`. `delete_photo` handles
   `FileNotFoundError` as a terminal case (filesystem.py:153-155), so double-
   deletion is safe. Document for future maintainers.

2. **CR-001 + MED-001 joint fix:** B1 ships both together (already in working
   tree). CR-001's guard makes `delete_draft` unreachable in the
   cancel-after-submit scenario; MED-001's `storage_keys()` fix ensures
   `delete_draft` is correct for the normal DRAFT cancel path.

3. **LOW-004 + HIGH-001 cache safety:** B9's long `max-age=31536000, immutable`
   cache is safe only when B2 (HIGH-001) ensures prompt file deletion on ad
   status change. B9 has a dependency on B2. If B2 has not shipped, B9
   should use a conservative short `max-age` (e.g. 3600) with revalidation.

4. **LOW-004 + LOW-002 staging/serving interaction:** If B3 (staging directory)
   ships, `_serve_image` resolves staging keys via `MEDIA_ROOT / staging/<key>` —
   the same path logic. No change needed in `_serve_image` or `media_gate`
   (staging files are never served via media_gate — only AdImage-referenced
   PUBLISHED keys are served).

5. **B7 + B9 shared edit:** Both modify `_serve_image` in `listings.py`. B7 must
   ship first. B9's cache-control headers are set on the response object
   returned by `media_gate` / `_serve_image`. Since `FileResponse` subclasses
   `HttpResponse`, header-setting code (`response["Cache-Control"] = ...`) works
   identically regardless of return type. But B9 should be tested against the
   B7 code path (FileResponse), and B9's `depends_on` includes `b7_serve_image_fix`.

6. **B1 + B3 same-file overlap:** B3 modifies `save_photo` and `process_photos`
   in `ad_create.py` — the same file B1 modifies. B1 must be committed before
   B3's Implementor edits `save_photo`. This is enforced by B3's
   `depends_on: [b1_cancel_flow_fix]`.

7. **B2 + B5 independent model changes:** B2 adds a signal (no model field
   change); B5 adds indexes to `AdImage.Meta`. B5's migration is additive and
   backward-compatible. No conflict — both can ship in Phase 1 if the
   Implementor has capacity, but B5 requires a migration run while B2 does not.

---

## 9. Audit Trail of Corrections

This section documents every correction applied to the original plan
(`.ai/plans/20-media-findings-fix.md`):

| # | Correction | Original plan reference | Corrected in this plan |
|---|---|---|---|
| C1 | B1 already in working tree — task is commit + tests, not re-implement | §3 Block B1 implementation_sequence steps 1-4 | §5 Block B1: steps restructured to commit → tests → validate; step 2 (`_get_ad_status` helper) marked as already-existing |
| C2 | `test_media_security.py` path is `ads/tests/`, not `media/tests/` | Plan `related:` list line 39, B6 B7 B9 inline citations | §0.3 + §5 B6/B7/B9 all use `src/backend/apps/ads/tests/test_media_security.py` |
| C3 | Test class name `TestProcessPreview` → `TestProcessPreviewLanguageDetection` | B1 acceptance_criteria line 241 | §5 B1 required_tests: corrected to `TestCancelAfterSubmit` (new class) |
| C4 | `test_orphaned_file_deleted` → `test_orphaned_file_is_deleted` | B8 required_tests line 1038 | §5 B8 acceptance_criteria + required_tests: corrected |
| C5 | `test_seed_files_preserved` → `test_seed_subdir_excluded` | B8 required_tests line 1039 | §5 B8 acceptance_criteria + required_tests: corrected |
| C6 | B7 + B9 share `_serve_image` — B7 must ship first | B7 and B9 listed as independent | §5 B7: "B7 must ship before B9" in acceptance_criteria; §5 B9: `depends_on` includes `b7_serve_image_fix` |
| C7 | B2 → B9 dependency (soft, for cache safety) | B9 depends_on only lists B2 | §5 B9: `depends_on: [b2_adimage_signal, b7_serve_image_fix]` with soft-dependency note |
| C8 | `IX_ads_pub_condition` documented in db-indexes.md but missing from code | Not flagged in original plan | §0.7 + §5 B5: advisory noted, out of scope, do NOT add |
| C9 | Verification report `.ai/audit/99-validation/07-media-verification-report.md` does not exist | Plan frontmatter line 5 | §0.6: noted as non-existent; Auditor's findings are authoritative |
| C10 | Line number drift (~2-10 lines from Sep-12 audit) | Multiple inline line references | §3 Phase/Ordering intro + §5 B3: noted drift; all references use semantic anchors or "current codebase" |
| C11 | `_get_ad_status` helper already exists in working tree | B1 implementation_sequence step 2 "Add `_get_ad_status` helper" | §5 B1 implementation_sequence: step 2 removed (already exists) |
| C12 | B1 commit must be isolated from PII-consent working changes | Not addressed in original plan | §5 B1: selective git add instructions; risk note on commit hygiene |
| C13 | Test file for B8 dead-code removal: `test_sweep_orphaned_media.py` at `media/tests/` (correct) | B8 cites `test_sweep_orphaned_media.py` | Confirmed correct at `src/backend/apps/media/tests/test_sweep_orphaned_media.py` |
