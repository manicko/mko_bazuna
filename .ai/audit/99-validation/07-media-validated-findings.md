---
# Report metadata — validated per Phase 99.
phase: "07"
phase_name: "Media subsystem audit"
date: "2026-09-12"
auditor: "Kilo (poolside/laguna-s-2.1:free)"
validator: "validator (Phase 99)"
mode: "problems-only"
id_prefix: "MEDIA"
report_status: "validated"
severity_taxonomy: ".kilo/commands/audit/phases/99-audit-validate.md"
---

# Audit Findings (Validated) — Media Subsystem

> **Validator's note.** This report is self-contained: every finding below was
> checked against the live source tree (`src/telegram_bot/handlers/ad_create.py`,
> `src/backend/apps/ads/models.py`, `src/backend/apps/ads/views/listings.py`,
> `src/backend/apps/media/services/filesystem.py`,
> `src/backend/apps/media/management/commands/sweep_orphaned_media.py`,
> `src/backend/apps/core/management/commands/sweep_drafts.py`,
> `src/backend/apps/ads/services/submission.py`,
> `src/backend/apps/moderation/services/auto_moderation.py`,
> `src/backend/apps/users/services/deletion.py`,
> `src/backend/apps/core/management/commands/consent_hard_delete.py`), the spec
> documents (`docs/02-database/db-retention.md`, `docs/02-database/db-indexes.md`,
> `docs/01-spec/technical-specification.md`, `docs/04-user-stories/seller-stories.md`),
> and the test suites (`test_sweep_commands.py`, `test_media_security.py`,
> `test_ad_create.py`). Each finding carries an inline **Validation** block
> stating the action taken, the validation type (`SPEC-DEVIATION` /
> `BEST-PRACTICE` / `DOC-UPDATE`), the evidence surveyed, and any
> source-reference drift from the original audit.
>
> Cross-phase note: MED-004 is a duplicate of **AD-004** (Phase 05 — Ad
> Lifecycle). Phase 05 already validated the same root cause (db-retention.md
> lists DRAFT retention as 7 days; code + phase spec define 30 minutes) as a
> `DOC-UPDATE`. This report defers to that decision and reclassifies MED-004
> accordingly. See [Phase 05 validated report](/05-ad-lifecycle-validated-findings.md#AD-004).

## Executive Summary

The media subsystem has a solid architectural foundation with well-structured
services (`AdImageService`, `ThumbnailService`, `Filesystem`), proper
path-traversal defenses in `media_gate`, and TX-then-Filesystem ordering in
sweep commands. However, several critical data-integrity and data-loss risks
were identified.

- **1 CRITICAL** — After successful ad submission, `state.clear()` is not
  called; a subsequent `/cancel` destroys the original image files of a
  published/on-moderation ad and orphans thumbnails.
- **2 HIGH** — No model-level physical file cleanup on `AdImage` cascade-delete
  (relying entirely on each sweep command's manual key collection); the orphan
  sweep classifies in-flight FSM-uploaded files as orphans and deletes them.
- **4 MEDIUM** — `delete_draft` skips thumbnail cleanup; full Telegram download
  before size validation; no DB indexes on `AdImage` lookup fields used by
  `media_gate`; DRAFT retention doc/code mismatch.
- **4 LOW** — Incomplete EXIF strip (`icc_profile` not removed);
  `_serve_image` docstring claims `FileResponse` but uses `HttpResponse`; dead
  code in `_walk_media_files`; no cache-control headers on `media_gate`.

> **Note:** The original executive summary states "3 LOW" but lists 4 LOW items.
> The summary table below correctly lists 4 LOW findings. Corrected here.

**Validation posture:** of 11 findings, **10 are Validated (unchanged)** and
**1 is Reclassified** (MED-004 → DOC-UPDATE, severity lowered to LOW, matching
Phase 05 AD-004). No findings are rejected — all remain applicable to the live
codebase.

---

## Scope & Methodology

**Scope:** Image upload, storage, serving, thumbnail lifecycle, orphan cleanup,
retention sweeps — covering the Telegram bot ad-creation FSM
(`src/telegram_bot/handlers/ad_create.py`), the `AdImage` model
(`src/backend/apps/ads/models.py`), the `media_gate` access view
(`src/backend/apps/ads/views/listings.py`), the filesystem service
(`src/backend/apps/media/services/filesystem.py`), the orphan sweep
(`src/backend/apps/media/management/commands/sweep_orphaned_media.py`), the
draft sweep (`src/backend/apps/core/management/commands/sweep_drafts.py`), the
submission service (`src/backend/apps/ads/services/submission.py`), the
auto-moderation gate (`src/backend/apps/moderation/services/auto_moderation.py`),
user consent deletion (`src/backend/apps/users/services/deletion.py`), the
consent hard-delete command (`src/backend/apps/core/management/commands/consent_hard_delete.py`),
and the spec docs (`db-retention.md`, `db-indexes.md`, `technical-specification.md`,
`seller-stories.md`).

### Verification Performed

| Check | Method | Result |
|-------|--------|--------|
| CR-001: state.clear() absent on success path | Source inspection of `ad_create.py:838-856` | CONFIRMED — `state.clear()` only on failure branch (line 848) |
| CR-001: cmd_cancel deletes originals for non-DRAFT ads | Source inspection of `ad_create.py:105-123` + `delete_draft:875-896` | CONFIRMED — `delete_photo(photo["storage_key"])` in FSM loop; `delete_draft` early-returns on non-DRAFT |
| HIGH-001: No delete() override or signal on AdImage | Source inspection of `models.py:521-686`; grep for `post_delete`/`@receiver` in media + ads apps | CONFIRMED — `save()` at 625, `storage_keys()` at 672; no `delete()`, no signals registered |
| HIGH-002: Orphan sweep only checks AdImage rows | Source inspection of `sweep_orphaned_media.py:88-92`; `ad_create.py:681-711` | CONFIRMED — `_collect_referenced_keys()` queries AdImage only; `save_photo()` writes to disk before submit_ad creates rows |
| MED-001: delete_draft uses img.image not storage_keys() | Source inspection of `ad_create.py:891-892` vs sweep commands | CONFIRMED — `delete_photo(img.image)` only; every sweep command uses `img.storage_keys()` |
| MED-002: download before validate_photo | Source inspection of `ad_create.py:681-695`; `filesystem.py:75-118` | CONFIRMED — `download_photo()` at 681, `validate_photo()` at 690; `PhotoSize.file_size` available but unused |
| MED-003: No indexes on AdImage lookup fields | Source inspection of `models.py:597-620`; `db-indexes.md:248-251` | CONFIRMED — only `db_index=True` on `sha256`; `image`/`thumbnail_*` unindexed |
| MED-004: 30 min vs 7 days | `sweep_drafts.py:45`; `db-retention.md:21,32,82`; phase 05 AD-004 validation | CONFIRMED — code: 30 min; db-retention.md: 7 days; phase spec: 30 min; test codifies 30 min |
| LOW-001: icc_profile not stripped | Source inspection of `filesystem.py:193-211` | CONFIRMED — only `img.info.pop("exif")` at 208; `icc_profile` persists through `exif_transpose` + `save` |
| LOW-002: docstring vs code mismatch | Source inspection of `listings.py:100-117`; imports at line 20 | CONFIRMED — docstring says FileResponse (103); code: `f.read()` + `HttpResponse` (116-117); `FileResponse` not imported |
| LOW-003: dead code in _walk_media_files | Source inspection of `sweep_orphaned_media.py:46-60` | CONFIRMED — lines 51-53 are a no-op `if/pass` block; seed exclusion at 55-56 |
| LOW-004: No cache-control on media_gate | Source inspection of `listings.py:120-198`; grep for `never_cache`/`cache_control` | CONFIRMED — no decorators, no headers; other public views use `never_cache` |

**Tools used:** direct source inspection (via `read`/`grep`), spec doc cross-
reference, cross-phase consistency check against `.ai/audit/99-validation/05-
ad-lifecycle-validated-findings.md`. No runtime repros were needed — these are
all static-code findings that do not require a database.

---

## Findings Summary

| ID | Title | Severity | Effort | Type (validated) | Status |
|----|-------|----------|--------|-------------------|--------|
| CR-001 | Cancel after submit destroys ad images | CRITICAL | Small | SPEC-DEVIATION | Validated |
| HIGH-001 | No file cleanup on AdImage cascade-delete | HIGH | Small | SPEC-DEVIATION | Validated |
| HIGH-002 | Orphan sweep deletes in-flight uploads | HIGH | Medium | SPEC-DEVIATION | Validated |
| MED-001 | `delete_draft` doesn't delete thumbnails | MEDIUM | Trivial | BEST-PRACTICE | Validated |
| MED-002 | Telegram download before size validation | MEDIUM | Small | BEST-PRACTICE | Validated |
| MED-003 | No DB indexes on AdImage lookup fields | MEDIUM | Small | BEST-PRACTICE | Validated |
| MED-004 | DRAFT retention mismatch (30 min vs 7 days) | ~~MEDIUM~~ → LOW | Trivial | ~~SPEC-DEVIATION~~ → DOC-UPDATE | Reclassified |
| LOW-001 | Incomplete EXIF strip (icc_profile) | LOW | Trivial | BEST-PRACTICE | Validated |
| LOW-002 | `_serve_image` docstring/code mismatch | LOW | Trivial | DOC-UPDATE | Validated |
| LOW-003 | Dead code in `_walk_media_files` | LOW | Trivial | BEST-PRACTICE | Validated |
| LOW-004 | No cache-control on media responses | LOW | Small | BEST-PRACTICE | Validated |

---

## Findings by Severity

### CRITICAL

> **Validation:** ✅ **Validated — SPEC-DEVIATION (no change).**
> Confirmed by direct source inspection.
>
> **Evidence surveyed:**
> - `ad_create.py:838-850` — On success (`is_valid` is True), `state.clear()`
>   is **not** called. It appears only in the `else` (failure) branch at line 848.
> - `ad_create.py:106-123` — `cmd_cancel` retrieves `data["photos"]` from FSM
>   state (still present after successful submit because state was never cleared),
>   iterates and calls `delete_photo(photo["storage_key"])` for each original,
>   then calls `delete_draft(data["ad_id"])`, then `state.clear()`.
> - `ad_create.py:875-896` — `delete_draft` fetches
>   `Ad.objects.get(id=ad_id, status=AdStatus.DRAFT)`. Since `submit_ad`
>   transitions the ad to `ON_MODERATION` (submission.py:179) and `auto_moderate`
>   may further transition to `PUBLISHED` (auto_moderation.py:166-170), the
>   ad is no longer DRAFT → `DoesNotExist` → early return, no deletion.
> - `submission.py:167-179` — `AdImageService.create_or_skip()` creates `AdImage`
>   rows inside `transaction.atomic()` using the FSM `photos` storage keys.
>   Thumbnails are generated at submission.py:137-155, before the DB transaction.
> - `auto_moderation.py:94-170` — `auto_moderate(ad)` can transition the ad to
>   `PUBLISHED` via `_pass_moderation` (line 166), which calls
>   `set_published` → `ad.transition_to(AdStatus.PUBLISHED)`.
>
> **Scenario confirmed:** (1) User uploads photos → keys stored in FSM `photos`.
> (2) User types "confirm" → `submit_ad()` creates `AdImage` rows + thumbnails,
> transitions DRAFT→ON_MODERATION→(maybe PUBLISHED), but `state.clear()` is
> NOT called on success. (3) User types "cancel" → `cmd_cancel` deletes original
> photo files from disk via FSM `photos` list, `delete_draft` returns early
> (ad not DRAFT), `state.clear()` runs. (4) Result: original image files
> destroyed, `AdImage` rows point to deleted files, thumbnails orphaned.
>
> **Spec reference:** `seller-stories.md:38-39` — "Preview before send; ...
> Send 'confirm' to submit for moderation or 'cancel' to abort." The spec
> implies cancel operates on the *draft* flow, not a *submitted* ad. The code
> allows cancel to destroy a submitted ad's media — a data-loss deviation.
>
> **Recommendation (from findings):** Add `state.clear()` after successful
> `submit_ad`, and guard `cmd_cancel` to skip photo deletion when the ad is no
> longer DRAFT. Both parts are valid and necessary (defense-in-depth).
>
> **Source-reference drift:** The findings' evidence snippets are paraphrased
> (not byte-exact), but line numbers and behavior are accurate. The
> `process_preview` success path at actual line 838-841 sends
> "Ad submitted for moderation! You'll be notified when it's published." (the
> finding shows a shortened message "Ad submitted for moderation!"). No
> substantive content drift.

#### CR-001: [CRITICAL] — Cancel after successful submit destroys ad images

| Field | Value |
|---|---|
| **ID** | CR-001 |
| **Title** | Cancel after successful submit destroys ad images |
| **Severity** | CRITICAL |
| **File(s)** | `src/telegram_bot/handlers/ad_create.py:838-853` (success path); `:105-123` (cancel); `:875-896` (delete_draft) |
| **Spec reference** | `docs/04-user-stories/seller-stories.md:38-39` |
| **Status** | Open |
| **Validation Type** | SPEC-DEVIATION |
| **Problem** | After `submit_ad()` succeeds, `state.clear()` is NOT called on the success path (ad_create.py:838-850; `state.clear()` appears only at line 848 in the failure branch). The FSM state retains `ad_id` and `photos` (original image storage keys). When the user subsequently types "cancel" or sends `/cancel`, `cmd_cancel()` (line 106) retrieves the stale `photos` list and calls `delete_photo(photo["storage_key"])` for each original file — destroying the physical files of a successfully submitted ad. `delete_draft()` (line 875) returns early because the ad is no longer DRAFT (it was transitioned to ON_MODERATION by submit_ad at submission.py:179, and possibly PUBLISHED by auto_moderate). `state.clear()` at line 121 then clears the FSM. Result: original image files destroyed on disk while `AdImage` DB rows remain pointing to deleted files; thumbnails also orphaned. |
| **Impact** | A buyer could encounter broken image links on a published ad if the seller mistakenly types "cancel" after confirming. Complete data loss of submitted ad media. |
| **Root Cause** | Success path omits `state.clear()` and `cmd_cancel` unconditionally deletes photos from FSM state without checking whether the ad is still in DRAFT. |
| **Recommendation** | (1) Call `state.clear()` immediately after successful `submit_ad` (after line 841). (2) Guard `cmd_cancel` to only delete photos when the ad is still DRAFT — check the ad's status before iterating the FSM `photos` list. |
| **Effort** | Small |
| **Priority** | Mandatory |

**Evidence — `src/telegram_bot/handlers/ad_create.py:838-850`** *(success path does not clear state)*:
```python
        if is_valid:
            await message.answer(
                "Ad submitted for moderation! You'll be notified when it's published."
            )
            # ↑ state.clear() NOT called here — FSM state persists with ad_id + photos
        else:
            await message.answer(
                "Ad failed moderation. Please check your content and try again."
            )

            await state.clear()    # ← only reached on failure

            return
```

**Evidence — `src/telegram_bot/handlers/ad_create.py:105-123`** *(cancel deletes originals unconditionally)*:
```python
async def cmd_cancel(message: types.Message, state: FSMContext) -> None:
    """Cancel ad creation."""

    data = await state.get_data()

    if "ad_id" in data:
        # Clean up photo files from FSM state before deleting the draft

        photos = data.get("photos", [])

        for photo in photos:
            await asyncio.to_thread(delete_photo, photo["storage_key"])  # ← deletes originals

        await delete_draft(data["ad_id"])  # ← returns early (ad not DRAFT)

    await state.clear()

    await message.answer("Ad creation cancelled.")
```

**Evidence — `src/telegram_bot/handlers/ad_create.py:875-896`** *(delete_draft early-returns on non-DRAFT)*:
```python
async def delete_draft(ad_id: int) -> None:
    """Delete a draft ad and clean up its photo files."""

    @sync_to_async
    def _delete() -> None:
        try:
            ad = Ad.objects.get(id=ad_id, status=AdStatus.DRAFT)
        except Ad.DoesNotExist:
            return  # ← ad already transitioned to ON_MODERATION/PUBLISHED
        for img in ad.images.all():
            delete_photo(img.image)
        ad.delete()

    await _delete()
```

**Evidence — `src/backend/apps/ads/services/submission.py:178-179`** *(submit_ad transitions DRAFT→ON_MODERATION)*:
```python
        # Transition DRAFT -> ON_MODERATION (state machine requires this step)
        ad.transition_to(AdStatus.ON_MODERATION)
```

**Evidence — `src/backend/apps/moderation/services/auto_moderation.py:164-170`** *(auto_moderate may further transition to PUBLISHED)*:
```python
    # All checks passed - publish
    try:
        _pass_moderation(ad)
    except MaxAdsExceeded:
        _fail_moderation(ad)
        return False
    return True
```

**Related Findings:** MED-001 (thumbnail orphan in the same cancel flow); HIGH-002 (orphan sweep as backstop)

---

### HIGH

> **Validation:** ✅ **Validated — SPEC-DEVIATION (no change).** Confirmed by source inspection. No `delete()` override or `post_delete`/`pre_delete` signal exists on `AdImage`. Grep for `post_delete` and `@receiver` across `src/backend/` returned signal registrations only for `categories.Category`/`CategoryPath`/`CategoryListingPurpose`/etc. and `lookups.LookupGroup`/`LookupItem` — none for `AdImage` or `Ad`.
>
> **Evidence surveyed:**
> - `models.py:521-686` — `AdImage` defines `save()` (625), `storage_keys()` (672), and four `image_url`/`thumbnail_*_url` properties (649-670). No `delete()` method. `AdImage.Meta` (597-620) has only check constraints + `db_index=True` on `sha256`; no `indexes` list, no signal dispatch.
> - `ad_create.py:894` — `delete_draft` calls `ad.delete()` on a DRAFT ad, triggering ORM cascade that removes `AdImage` DB rows but not physical files (though `delete_draft` pre-deletes `img.image` only, not thumbnails — see MED-001).
> - `sweep_drafts.py:63-76`, `delete_sweep.py:63-78`, `purge_failed_ads.py:62-77`, `purge_rejected_ads.py:63-79`, `purge_deleted_ads.py:63-79`, `consent_hard_delete.py:69-93` — every sweep command manually collects `storage_keys()` *before* the transaction and calls `delete_photo()` *after* commit (TX-then-FS pattern). This proves the project *intends* physical file cleanup but relies entirely on each caller doing it manually, with no model-level safety net.
> - `deletion.py:165-221` — `soft_delete_user_ads` uses `img.storage_keys()` (line 201) for DRAFT ad cleanup. Confirmed.
>
> **Architectural consideration for fix:** A `post_delete` signal on `AdImage` would fire *inside* the transaction for individual `.delete()` calls. The project's established TX-then-FS pattern deletes files *after* `transaction.atomic()` commits. A naive signal-based approach would violate this. The correct implementation should use `pre_delete` to collect keys into a thread-local or list, then `transaction.on_commit()` to delete files — or, more simply, the signal handler should call `delete_photo()` wrapped in `transaction.on_commit(lambda: [delete_photo(k) for k in keys])`. This is an implementation detail, not a validation concern — the finding itself is valid.

> **Source-reference drift:** The finding references `models.py:521-670` for the AdImage class. The class actually spans 521-686 (extends slightly further than cited). `storage_keys()` is at line 672 (cited as "line 672"). No substantive drift.

#### HIGH-001: [HIGH] — No physical file cleanup on AdImage cascade-delete

| Field | Value |
|---|---|
| **ID** | HIGH-001 |
| **Title** | No physical file cleanup on AdImage cascade-delete |
| **Severity** | HIGH |
| **File(s)** | `src/backend/apps/ads/models.py:521-686` (AdImage model) |
| **Spec reference** | `docs/02-database/db-retention.md:102` (describes explicit `delete_photo()` loop with `storage_keys()` for consent hard-delete) |
| **Status** | Open |
| **Validation Type** | SPEC-DEVIATION |
| **Problem** | `AdImage` has `ad = ForeignKey(..., on_delete=models.CASCADE)` (line 529) but defines **no `delete()` override** and **no `post_delete`/`pre_delete` signal**. When an `Ad` is hard-deleted via the ORM, Django cascades and removes `AdImage` DB rows at the SQL level, but physical files (original + 3 thumbnails) are not cleaned up. The model defines `save()` (625) and `storage_keys()` (672) but no deletion hook. The only correct cleanup paths are the six sweep commands (`sweep_drafts`, `delete_sweep`, `purge_failed_ads`, `purge_rejected_ads`, `purge_deleted_ads`, `consent_hard_delete`) and `soft_delete_user_ads` — all of which manually collect `storage_keys()` *before* the DB transaction and delete files *after* commit (TX-then-FS). Any code path that calls `ad.delete()` or `AdImage.objects.filter(...).delete()` without manual key collection orphans physical files. |
| **Impact** | Physical files accumulate on disk until the next hourly orphan sweep. Disk usage grows unbounded for high-volume deployments. The hourly `sweep_orphaned_media` backstop mitigates this but creates a race window (see HIGH-002). |
| **Root Cause** | No model-level deletion hook complements the existing sweep-level cleanup. The TX-then-FS pattern is implemented manually per-sweeper, not centralized at the model layer. |
| **Recommendation** | Add a `pre_delete` signal on `AdImage` that collects `storage_keys()` and registers a `transaction.on_commit()` callback to call `delete_photo()` for each key — preserving the TX-then-FS pattern at the model layer. Alternatively, override `AdImage.delete()` to call `super().delete()` then schedule file removal after commit. |
| **Effort** | Small |
| **Priority** | Recommended |

**Evidence — `src/backend/apps/ads/models.py:521-686`** *(AdImage: save() + storage_keys(), no delete() override, no signals)*:
```python
class AdImage(models.Model):
    """Ad image with UUID v4 storage key for URL anonymity."""
    ad = models.ForeignKey(      # line 527
        Ad,
        on_delete=models.CASCADE,   # ← ORM cascade deletes DB rows only
        related_name="images",
    )
    # ... image, thumbnail_small/medium/large, sha256 fields (533-595) ...

    class Meta:                   # line 597
        db_table = "ad_images"
        ordering = ["position"]
        constraints = [...]       # ← only check constraints on key format
        # ↑ NO indexes list, NO signal dispatch

    def save(self, *args, **kwargs) -> None:    # line 625
        ...   # SHA-256 auto-compute

    def storage_keys(self) -> list[str]:        # line 672 — returns all keys
        ...

    # ↑ NO delete() method, NO post_delete signal receiver
```

**Evidence — sweep commands correctly use storage_keys() (contrast)**:
```python
# sweep_drafts.py:63-66 — correct pattern
storage_keys = [
    key
    for img in AdImage.objects.filter(ad_id__in=ad_ids)
    for key in img.storage_keys()  # ← all keys: image + thumbnails
]
```

**Related Findings:** MED-001 (same cancel-flow inconsistency), HIGH-002 (orphan sweep race window)

---

> **Validation:** ✅ **Validated — SPEC-DEVIATION (no change).** Confirmed by source inspection. The gap between disk-write and AdImage-creation is real and spans the upload flow.
>
> **Evidence surveyed:**
> - `ad_create.py:681-711` — `process_photos` (PHOTOS FSM step): downloads via
>   `download_photo()` (681), validates via `validate_photo()` (690), saves to
>   disk via `save_photo()` (699), then stores the key in FSM state
>   `photos.append({"storage_key": ...})` (703-709) and `state.update_data()`
>   (711). No `AdImage` row is created at this stage.
> - `submission.py:158-179` — `AdImageService.create_or_skip()` is called inside
>   `transaction.atomic()` (line 158) only during `submit_ad()`, which happens at
>   the "confirm" step — minutes after the photo was first written to disk.
> - `sweep_orphaned_media.py:34-43, 88-92` — `_collect_referenced_keys()` (line 34)
>   queries only `AdImage` rows (line 38: `AdImage.objects.values(*fields)`);
>   `_walk_media_files()` (line 46) walks `MEDIA_ROOT` unconditionally (excluding
>   only `seed/`). `orphans = on_disk - referenced` (line 92) classifies in-flight
>   upload files as orphans.
> - `db-retention.md:122-128` — scheduler runs sweeps hourly; each command is
>   individually advisory-locked, so concurrency between two sweep instances is
>   handled, but not between a sweep and an in-flight upload.
>
> **Architectural note:** The findings' evidence line refs (`ad_create.py:681-690`,
> `submission.py:167-176`, `sweep_orphaned_media.py:34-43` and `89-92`) are
> accurate in substance; the actual `_collect_referenced_keys` def spans lines
> 34-43 and the deletion loop at 108-111. No substantive drift.

#### HIGH-002: [HIGH] — Orphan sweep deletes in-flight uploads

| Field | Value |
|---|---|
| **ID** | HIGH-002 |
| **Title** | Orphan sweep deletes in-flight uploads |
| **Severity** | HIGH |
| **File(s)** | `src/backend/apps/media/management/commands/sweep_orphaned_media.py:34-43, 88-92` |
| **Spec reference** | `docs/02-database/db-retention.md:122-128` (hourly scheduler) |
| **Status** | Open |
| **Validation Type** | SPEC-DEVIATION |
| **Problem** | `sweep_orphaned_media` collects referenced keys exclusively from `AdImage` rows (`_collect_referenced_keys()` at line 34-43), then walks `MEDIA_ROOT` and deletes any file not in that set (line 92). However, the bot upload flow writes files to disk via `save_photo()` (ad_create.py:699) and stores keys in FSM state **before** `AdImage` rows are created during `submit_ad()` (submission.py:167-176). The upload flow — download (681) → validate (690) → save to disk (699) → FSM state (711) → ... → submit_ad creates AdImage rows (167-176) — can span minutes. If the hourly sweep runs mid-upload, the just-saved photo (on disk, FSM-only) is not in any `AdImage` row and is classified as an orphan and deleted. |
| **Impact** | In-flight photo uploads can be silently deleted by the hourly sweep. Sellers see "Photo saved" messages but encounter broken/missing images when they try to upload more photos or submit. Data loss, user-facing. |
| **Root Cause** | The orphan sweep has no visibility into the FSM-state upload stage — it assumes all non-orphan files are referenced by `AdImage` rows. There is no staging directory or pending-upload tracking. |
| **Recommendation** | Accept uploads into a staging subdirectory (e.g. `staging/`) excluded from the orphan sweep; move files to permanent storage on successful `submit_ad`. Alternatively, add a lightweight "pending uploads" registry (a model or cache set) that the sweep queries before deleting. |
| **Effort** | Medium |
| **Priority** | Recommended |

**Evidence — `src/telegram_bot/handlers/ad_create.py:679-711`** *(save to disk + FSM, no AdImage row)*:
```python
    # Download photo bytes for validation

    photo_bytes = await download_photo(photo.file_id, message.bot)        # step 2

    if not photo_bytes:
        await message.answer("Failed to download photo. Try again.")
        return

    # Validate photo

    is_valid, error = validate_photo(photo_bytes)

    if not is_valid:
        await message.answer(f"Invalid: {error}")
        return

    # Store photo

    storage_key = await save_photo(generate_storage_key(), photo_bytes)   # step 3: file on disk

    # Save to state

    photos.append(
        {
            "storage_key": storage_key,
            "telegram_file_id": photo.file_id,
            "position": len(photos),
        }
    )

    await state.update_data(photos=photos)                                 # step 4: FSM state only
```

**Evidence — `src/backend/apps/ads/services/submission.py:167-179`** *(AdImage row created only here, inside TX)*:
```python
        # Create AdImage records with pre-generated thumbnails
        for photo in input.photos:
            AdImageService.create_or_skip(
                ad=ad,
                image=photo["storage_key"],
                ...
            )

        # Transition DRAFT -> ON_MODERATION (state machine requires this step)
        ad.transition_to(AdStatus.ON_MODERATION)
```

**Evidence — `src/backend/apps/media/management/commands/sweep_orphaned_media.py:88-92`** *(sweep only checks AdImage rows)*:
```python
        with advisory_lock(AdvisoryLockId.SWEEP_ORPHANED_MEDIA):
            referenced = _collect_referenced_keys()  # from AdImage rows only
            on_disk = set(_walk_media_files(media_root))  # includes in-flight uploads

    orphans = on_disk - referenced  # in-flight uploads classified as orphans
```

**Related Findings:** CR-001 (cancel-after-submit destroys submitted originals — different root cause but same file-cleanup surface), HIGH-001 (no model-level safety net)

---

### MEDIUM

> **Validation:** ✅ **Validated — BEST-PRACTICE (no change).** Confirmed by source inspection. `delete_draft` (ad_create.py:891-892) calls `delete_photo(img.image)` only. Every other deletion path — `sweep_drafts.py:63-66`, `delete_sweep.py:63-68`, `purge_failed_ads.py:62-66`, `purge_rejected_ads.py:63-65`, `purge_deleted_ads.py:63-65`, `consent_hard_delete.py:72-76`, `soft_delete_user_ads` in `deletion.py:198-202` — uses `img.storage_keys()`.
>
> **Practical impact nuance:** In the normal bot flow, DRAFT ads do not have `AdImage` rows (rows are created only in `submit_ad()`, which transitions away from DRAFT). So `ad.images.all()` is typically empty in `delete_draft`, making this loop a no-op. The finding's impact ("thumbnails accumulate as orphans when drafts are cancelled") is only material if `AdImage` rows exist for a DRAFT ad — which is not the normal flow. Nevertheless, the code is inconsistent and fragile: if the flow changes (e.g., preview thumbnails generated for DRAFT ads), this path would silently orphan thumbnail files. The recommendation to use `storage_keys()` is valid and aligns with the established pattern.

#### MED-001: [MEDIUM] — `delete_draft` does not delete thumbnail files

| Field | Value |
|---|---|
| **ID** | MED-001 |
| **Title** | `delete_draft` does not delete thumbnail files |
| **Severity** | MEDIUM |
| **File(s)** | `src/telegram_bot/handlers/ad_create.py:875-896` |
| **Spec reference** | `docs/02-database/db-retention.md:102` (describes `storage_keys()` usage for cleanup) |
| **Status** | Open |
| **Validation Type** | BEST-PRACTICE |
| **Problem** | `delete_draft` iterates `ad.images.all()` and calls `delete_photo(img.image)` (line 892) for each image — deleting only the original file. It does **not** delete thumbnail variants (`thumbnail_small`, `thumbnail_medium`, `thumbnail_large`). The `AdImage.storage_keys()` method (models.py:672) returns all keys including thumbnails, but it is not used here. This is inconsistent: `sweep_drafts.py:66`, `soft_delete_user_ads` (deletion.py:201), `consent_hard_delete.py:75`, `delete_sweep.py:68`, `purge_failed_ads.py:67`, `purge_rejected_ads.py:67`, and `purge_deleted_ads.py:67` all correctly use `img.storage_keys()`. `delete_draft` is the only deletion path that does not. |
| **Impact** | Thumbnail files would accumulate as orphans if `delete_draft` encounters `AdImage` rows with thumbnails. In the current normal flow, DRAFT ads have no `AdImage` rows (created only during `submit_ad`), so this is a latent inconsistency rather than an active data-loss path. The hourly `sweep_orphaned_media` eventually reclaims any orphaned thumbnails. |
| **Root Cause** | `delete_draft` uses `img.image` directly instead of the established `storage_keys()` pattern, likely an oversight during initial implementation. |
| **Recommendation** | Replace `delete_photo(img.image)` with iteration over `img.storage_keys()`. |
| **Effort** | Trivial |
| **Priority** | Recommended |

**Evidence — `src/telegram_bot/handlers/ad_create.py:891-892`** *(only original key deleted)*:
```python
        for img in ad.images.all():
            delete_photo(img.image)  # ← only original, NOT storage_keys()
```

**Evidence — contrast: `src/backend/apps/core/management/commands/sweep_drafts.py:63-66`** *(correct pattern)*:
```python
                storage_keys = [
                    key
                    for img in AdImage.objects.filter(ad_id__in=ad_ids)
                    for key in img.storage_keys()  # ← all keys: image + thumbnails
                ]
```

**Related Findings:** CR-001 (cancel-after-submit destroys originals — `cmd_cancel` also only iterates FSM `photos` originals, not thumbnail keys)

---

> **Validation:** ✅ **Validated — BEST-PRACTICE (no change).** Confirmed by source inspection. The download-before-validation flow is real, and `PhotoSize.file_size` is available but unused.
>
> **Evidence surveyed:**
> - `ad_create.py:681` — `photo_bytes = await download_photo(photo.file_id, message.bot)` downloads the full file before any validation.
> - `ad_create.py:690` — `is_valid, error = validate_photo(photo_bytes)` checks size (≤2MB) and dimensions AFTER download.
> - `ad_create.py:663` — `photo = message.photo[-1]` retrieves the largest `PhotoSize`, which includes `file_size` (Telegram Bot API `PhotoSize` type: `file_id`, `file_unique_id`, `width`, `height`, `file_size` optional). Grep for `file_size` across the entire `src/` tree returned **zero matches** — confirming it is never checked.
> - `filesystem.py:99` — `validate_photo` checks `len(photo_bytes) > 2 * 1024 * 1024` (2MB max).
> - `ad_create.py:675` — `check_upload_rate_limit(user_id)` is a per-user-per-window rate limit, not a file-size guard.
>
> **Nuance on recommendation:** Checking `photo.file_size` before download is valid but has a caveat: `file_size` is `Optional[int]` in the Telegram API and may be `None` for some uploads. The fix should handle `None` by falling back to download-then-validate. Additionally, `file_size` is a Telegram-reported value (not a security boundary — a malicious client could potentially manipulate it at the Telegram layer), so the post-download `validate_photo` size check must remain. The recommendation is sound as a defense-in-depth optimization.

#### MED-002: [MEDIUM] — Telegram photo downloaded before size validation

| Field | Value |
|---|---|
| **ID** | MED-002 |
| **Title** | Telegram photo downloaded before size validation |
| **Severity** | MEDIUM |
| **File(s)** | `src/telegram_bot/handlers/ad_create.py:681-695` |
| **Status** | Open |
| **Validation Type** | BEST-PRACTICE |
| **Problem** | The `process_photos` handler (PHOTOS FSM step) downloads the full photo bytes via `download_photo()` (line 681) **before** calling `validate_photo()` (line 690). `validate_photo` checks the ~2MB size limit (filesystem.py:99). Telegram's Bot API does not support range requests on `file_id` downloads, so the entire file is fetched into bot memory before the size check rejects it. A malicious or buggy client can send arbitrarily large files, consuming bot memory and bandwidth. |
| **Impact** | Memory exhaustion vector for the bot process. A user could upload a 50MB file, consuming bot memory and bandwidth, before the size check rejects it. |
| **Root Cause** | Telegram's `PhotoSize` object reports `file_size`, but the handler never checks it before initiating the download. |
| **Recommendation** | Check `photo.file_size` (Telegram provides this on `PhotoSize`) before calling `download_photo()`. If `file_size` exceeds the max (or is None), reject immediately or fall back to download-then-validate. Additionally, use streaming download with a byte cap as a second layer of defense. |
| **Effort** | Small |
| **Priority** | Recommended |

**Evidence — `src/telegram_bot/handlers/ad_create.py:681-695`**:
```python
    # Download photo bytes for validation

    photo_bytes = await download_photo(photo.file_id, message.bot)  # full download

    if not photo_bytes:
        await message.answer("Failed to download photo. Try again.")

        return

    # Validate photo

    is_valid, error = validate_photo(photo_bytes)  # size check happens here
```

**Evidence — `src/backend/apps/media/services/filesystem.py:75-100`** *(validate_photo checks size post-download)*:
```python
    # Check approximate size (~2MB max)
    if len(photo_bytes) > 2 * 1024 * 1024:
        return False, "Photo too large. Maximum size is approximately 2MB."
```

**Evidence — `photo.file_size` is available but never used:**
> Grep for `file_size` across `src/` returns zero matches. The `PhotoSize` type from aiogram 3.x includes `file_size: Optional[int]`, and `photo = message.photo[-1]` (ad_create.py:663) is a `PhotoSize`. The attribute exists but is unchecked.

---

> **Validation:** ✅ **Validated — BEST-PRACTICE (no change).** Confirmed by source inspection. No `indexes` entry exists in `AdImage.Meta`. The `db-indexes.md` spec only documents `IX_adimages_sha256` (for dedup); it does not list indexes for `image`/`thumbnail_*` fields, so their absence is not a doc-vs-code contradiction — it is an untracked performance gap.
>
> **Evidence surveyed:**
> - `models.py:597-620` — `AdImage.Meta` has `db_table`, `ordering`, and `constraints` (check constraints on key format). NO `indexes` list. Only `sha256` has `db_index=True` (line 591).
> - `listings.py:169-178` — `media_gate` queries with an OR across `image`, `thumbnail_small`, `thumbnail_medium`, `thumbnail_large` (lines 169-173), then a second query filtering on `ad__status=PUBLISHED` (line 190). Neither field is indexed.
> - `db-indexes.md:248-251` — documents only `IX_adimages_sha256`; no mention of image/thumbnail indexes. The "no index" note on db-retention.md:32 is for the Ad table's DRAFT sweep, not AdImage.
> - `test_media_security.py:169-265, 438-586` — tests confirm the OR-query pattern and thumbnail key resolution through `media_gate`.

#### MED-003: [MEDIUM] — No DB indexes on AdImage lookup fields

| Field | Value |
|---|---|
| **ID** | MED-003 |
| **Title** | No DB indexes on AdImage lookup fields |
| **Severity** | MEDIUM |
| **File(s)** | `src/backend/apps/ads/models.py:597-620` (AdImage.Meta); `src/backend/apps/ads/views/listings.py:169-178` (media_gate query) |
| **Spec reference** | `docs/02-database/db-indexes.md:248-251` |
| **Status** | Open |
| **Validation Type** | BEST-PRACTICE |
| **Problem** | `AdImage.Meta` defines only `constraints` (check constraints on key format) and `db_index=True` on `sha256` (line 591). There are **no `indexes`** entries. The `media_gate` view queries by `image` and `thumbnail_small/medium/large` with OR conditions on every image request (listings.py:169-177), then a second query for the published-check (line 190). Without indexes on these fields, every image request triggers sequential scans on the `ad_images` table. |
| **Impact** | Image request latency scales poorly with `ad_images` table size. On a production listing page with 24 ads × 3 images, each image request does 2 unindexed queries — a sequential scan on every thumbnail load. |
| **Root Cause** | No indexes were added for the `media_gate` lookup fields; `db-indexes.md:248-251` only documents `IX_adimages_sha256` for deduplication. |
| **Recommendation** | Add `models.Index(...)` entries to `AdImage.Meta.indexes` for `image`, `thumbnail_small`, `thumbnail_medium`, and `thumbnail_large`. PostgreSQL can use bitmap scans across multiple B-tree indexes for OR conditions. Consider a composite or expression index if one lookup pattern dominates. |
| **Effort** | Small (add index entries, generate migration) |
| **Priority** | Recommended |

**Evidence — `src/backend/apps/ads/models.py:597-620`** *(no indexes list)*:
```python
    class Meta:
        db_table = "ad_images"
        ordering = ["position"]
        constraints = [
            models.CheckConstraint(...),  # ck_ad_images_image_key_format
            models.CheckConstraint(...),  # ck_ad_images_thumb_small_key_format
            models.CheckConstraint(...),  # ck_ad_images_thumb_medium_key_format
            models.CheckConstraint(...),  # ck_ad_images_thumb_large_key_format
        ]
        # ↑ NO indexes list — image, thumbnail_small/medium/large are unindexed
```

**Evidence — `src/backend/apps/ads/views/listings.py:169-178`** *(unindexed OR query per request)*:
```python
    key_q = (
        Q(image=image_key)
        | Q(thumbnail_small=image_key)
        | Q(thumbnail_medium=image_key)
        | Q(thumbnail_large=image_key)
    )

    if not AdImage.objects.filter(key_q).exists():   # ← sequential scan
        raise Http404("Image not found")
```

**Evidence — `docs/02-database/db-indexes.md:248-251`** *(spec only documents sha256 index)*:
```python
## Indexes — ad_images
models.Index(name="IX_adimages_sha256", fields=["sha256"])  # photo deduplication lookup
```

---

> **Validation:** ✅ **Reclassified — DOC-UPDATE (code correct, doc wrong).**
> This is a **cross-phase duplicate** of Phase 05 finding **AD-004**. The Phase 05
> validator already resolved this exact root cause (db-retention.md says 7 days;
> code + phase spec say 30 minutes) as a `DOC-UPDATE` with LOW severity.
>
> **Evidence surveyed:**
> - `sweep_drafts.py:45` — `cutoff_date = timezone.now() - timedelta(minutes=30)` (code = 30 min).
> - `db-retention.md:21` — "Single source of truth for how long each ad status
>   is retained before permanent deletion."
> - `db-retention.md:32` — `| DRAFT | 7 days | sweep_drafts | *(no index — full scan)*` (doc says 7 days).
> - `db-retention.md:82` — `sweep_drafts | *(none)* | 7 days | Delete DRAFT ads older than 7 days` (doc says 7 days).
> - `technical-specification.md:152` — "Abandoned drafts auto-deleted on idle
>   timeout (e.g. 30 min)." The "(e.g.)" marks this as an example, not authoritative.
> - `seller-stories.md:38-39` — "Abandoned drafts auto-deleted on idle timeout
>   (~30 min); no partial ads saved." (Phase 07 user story, confirms 30 min intent.)
> - `test_sweep_commands.py:189` — docstring: "Tests for sweep_drafts command
>   (advisory lock 4, 30-minute window)."
> - `test_sweep_commands.py:206` — `test_deletes_drafts_older_than_30_minutes` (test codifies 30 min).
> - **Cross-phase:** Phase 05 `05-audit-ad-lifecycle.md:73` retention table:
>   `| DRAFT | 30 minutes | purge |` — confirms the phase spec defines 30 minutes.
>   Phase 05 validation (AD-004): "phase spec 05-audit-ad-lifecycle.md:73 defines
>   DRAFT retention as 30 minutes. The doc contradicts both the implementation and
>   the spec. Code is correct; doc is outdated. Type: DOC-UPDATE."
>
> **Decision:** `db-retention.md` is internally contradictory — it claims to be
> the "single source of truth" (line 21) yet states 7 days for DRAFT, while the
> phase spec and user story both say 30 minutes (idle timeout). The 30-minute
> window is also a deliberate design choice: it bounds the orphaned-photo
> exposure from a crashed bot FSM (noted in Phase 05 AD-004's recommendation).
> The code is correct; `db-retention.md` lines 32 and 82 should be updated to
> "30 minutes" (or "30 min idle-timeout sweep").
>
> **Severity reclassification:** Lowered from MEDIUM to LOW. This is a doc
> correction, not a code defect. The 30-minute implementation matches the phase
> spec and user story; the user-experience impact (drafts purged after 30 min)
> is the *intended* behavior per `seller-stories.md:39`.

> **Validation Note:**
> - **Action:** reclassified
> - **Detail:** MED-004 is a cross-phase duplicate of Phase 05 AD-004. The Phase 05
>   validator already determined the code (30 min) is correct and `db-retention.md`
>   (7 days) is the outdated doc. Reclassified to DOC-UPDATE with LOW severity to
>   maintain cross-phase consistency. The code requires no change; only the doc.
> - **See also:** AD-004 (Phase 05 — `05-ad-lifecycle-validated-findings.md`)

#### MED-004: [LOW] — DRAFT retention policy mismatch (30 min vs 7 days) [RECLASSIFIED]

| Field | Value |
|---|---|
| **ID** | MED-004 |
| **Title** | DRAFT retention policy mismatch (30 min vs 7 days) |
| **Severity** | ~~MEDIUM~~ → **LOW** |
| **File(s)** | `src/backend/apps/core/management/commands/sweep_drafts.py:45` |
| **Spec reference** | `docs/02-database/db-retention.md:32,82` (7 days); `docs/01-spec/technical-specification.md:152` (30 min, "e.g."); `docs/04-user-stories/seller-stories.md:38-39` (~30 min) |
| **Status** | Open |
| **Validation Type** | ~~SPEC-DEVIATION~~ → **DOC-UPDATE** |
| **Problem** | `sweep_drafts` uses `timedelta(minutes=30)` (line 45) to determine which DRAFT ads to delete. `db-retention.md` (self-described as "single source of truth", line 21) specifies **7 days** for DRAFT retention (lines 32, 82). The technical-specification.md uses "(e.g. 30 min)" (line 152 — example notation). The user story `seller-stories.md:39` says "(~30 min)". The test suite documents "30-minute window" (test_sweep_commands.py:189, 206). |
| **Impact** | No data loss or correctness issue. The 30-minute window is the **intended** behavior per the phase spec and user story — it bounds orphaned-photo exposure from a crashed bot FSM. The `db-retention.md` doc is simply outdated. Engineers reading the doc believe drafts are retained for 7 days, skewing retention/GDPR expectations. |
| **Root Cause** | `db-retention.md` was not updated when the 30-minute DRAFT idle-timeout window was implemented. |
| **Recommendation** | Update `db-retention.md` line 32 and line 82 to read "30 minutes" (matching `sweep_drafts.py` and the phase spec). No code change required. Add a short note that the 30-min window bounds orphaned-photo exposure from a crashed bot FSM. |
| **Effort** | Trivial (doc edit) |
| **Priority** | P2 |

**Evidence — `src/backend/apps/core/management/commands/sweep_drafts.py:45`** *(code = 30 min)*:
```python
                # Query draft ads older than 30 minutes
                cutoff_date = timezone.now() - timedelta(minutes=30)
```

**Evidence — `docs/02-database/db-retention.md:32,82`** *(doc = 7 days)*:
```text
| DRAFT | 7 days | sweep_drafts | *(no index — full scan)* |
...
| sweep_drafts | *(none)* | 7 days | Delete DRAFT ads older than 7 days |
```

**Evidence — `docs/04-user-stories/seller-stories.md:38-39`** *(intentional 30 min idle timeout)*:
```text
Preview before send. Seller can fix mismatches ... Abandoned drafts auto-deleted on
idle timeout (~30 min); no partial ads saved.
```

**Evidence — `src/backend/apps/core/tests/test_sweep_commands.py:189,206`** *(test codifies 30 min)*:
```python
class TestSweepDrafts:
    """Tests for sweep_drafts command (advisory lock 4, 30-minute window)."""
    ...
    def test_deletes_drafts_older_than_30_minutes(self, seller, category, city):
```

**Related Findings:** AD-004 (Phase 05 — same root cause, already validated as DOC-UPDATE)

---

### LOW

> **Validation:** ✅ **Validated — BEST-PRACTICE (no change).** Confirmed by source inspection.
>
> **Evidence surveyed:**
> - `filesystem.py:193-211` — `strip_photo_exif` calls `img = ImageOps.exif_transpose(img)` (line 207), which creates a new image that **copies the original's `info` dict** (including `icc_profile`). It then calls `img.info.pop("exif", None)` (line 208) — removing only the EXIF segment, NOT `icc_profile`. On `img.save(buf, format="JPEG", optimize=True)` (line 210), Pillow writes `icc_profile` to the output if it's present in `img.info`.
> - The docstring (line 198) claims the function "also hardens against malicious JPEGs" — the hardening is incomplete.
> - `test_media_security.py:TestExifStripping` (lines 268-309) tests removal of EXIF Make/Model/GPSInfo tags but has **no assertion for `icc_profile`** removal.
> - `apps/media/tests/test_save_photo_exif.py` references `TestExifStripping` in its module docstring.

#### LOW-001: [LOW] — Incomplete EXIF/metadata stripping in `strip_photo_exif`

| Field | Value |
|---|---|
| **ID** | LOW-001 |
| **Title** | Incomplete EXIF/metadata stripping in `strip_photo_exif` |
| **Severity** | LOW |
| **File(s)** | `src/backend/apps/media/services/filesystem.py:193-211` |
| **Status** | Open |
| **Validation Type** | BEST-PRACTICE |
| **Problem** | `strip_photo_exif` (line 193) removes EXIF data via `img.info.pop("exif", None)` (line 208) but does **not** remove `icc_profile` from `img.info`. `ImageOps.exif_transpose(img)` (line 207) creates a new image that copies the original's `info` dict, preserving `icc_profile`. When Pillow re-encodes the JPEG (`img.save(buf, format="JPEG", optimize=True)`, line 210), any remaining `icc_profile` is written to the output file. |
| **Impact** | Low privacy/security risk: ICC profiles can embed camera manufacturer/model, color calibration data, and (in some profiles) serial numbers. File size may also be slightly larger. The function's docstring claims it "hardens against malicious JPEGs" but the stripping is incomplete. |
| **Root Cause** | `img.info` contains both `exif` and `icc_profile` keys; only `exif` is stripped. |
| **Recommendation** | Also pop `icc_profile`: `img.info.pop("icc_profile", None)` before saving. Optionally pass `exif=b""` to `save()` for thorough EXIF removal. |
| **Effort** | Trivial |
| **Priority** | Recommended |

**Evidence — `src/backend/apps/media/services/filesystem.py:193-211`**:
```python
def strip_photo_exif(photo_bytes: bytes) -> bytes:
    """
    Strip EXIF/metadata from a JPEG photo and re-encode it.
    ...
    This also hardens against malicious JPEGs.
    ...
    """
    img = Image.open(io.BytesIO(photo_bytes))
    img = ImageOps.exif_transpose(img)   # copies info dict, including icc_profile
    img.info.pop("exif", None)          # ← only EXIF removed, icc_profile remains
    buf = io.BytesIO()
    img.save(buf, format="JPEG", optimize=True)  # ← writes icc_profile if present
    return buf.getvalue()
```

**Evidence — test gap:** `test_media_security.py:268-309` (`TestExifStripping`) asserts EXIF Make/Model/GPS removal but has **no assertion for `icc_profile`** removal.

---

> **Validation:** ✅ **Validated — DOC-UPDATE (no change).** Confirmed by source inspection. The docstring claims `FileResponse` streaming, but the code reads the entire file into memory and returns `HttpResponse`. `FileResponse` is not imported.
>
> **Evidence surveyed:**
> - `listings.py:100-117` — `_serve_image` docstring (line 103): "Uses `FileResponse` to stream the file from `MEDIA_ROOT`." Actual code (lines 115-117): `data = f.read()` then `return HttpResponse(data, content_type="image/jpeg")` — reads entire file into memory.
> - `listings.py:20` — imports: `from django.http import Http404, HttpRequest, HttpResponse, HttpResponseForbidden`. `FileResponse` is **not** imported.
> - `listings.py:120-198` — `media_gate` calls `_serve_image(image_key)` only when `settings.DEBUG` is True (lines 182, 194); production uses `X-Accel-Redirect`.

#### LOW-002: [LOW] — `_serve_image` docstring claims FileResponse but uses HttpResponse

| Field | Value |
|---|---|
| **ID** | LOW-002 |
| **Title** | `_serve_image` docstring claims FileResponse but uses HttpResponse |
| **Severity** | LOW |
| **File(s)** | `src/backend/apps/ads/views/listings.py:100-117` |
| **Status** | Open |
| **Validation Type** | DOC-UPDATE |
| **Problem** | The `_serve_image` function docstring (line 103) states "Uses `FileResponse` to stream the file from `MEDIA_ROOT`." However, the implementation reads the entire file into memory (`data = f.read()`, line 116) and wraps it in `HttpResponse(data, content_type="image/jpeg")` (line 117). `FileResponse` is not even imported (line 20). This is a development-only fallback (used when `DEBUG=True`), but the mismatch creates maintenance confusion and causes memory pressure when serving large images in development. |
| **Impact** | Memory inefficiency in development. Doc/code mismatch creates maintenance confusion. |
| **Root Cause** | The docstring was written for the intended `FileResponse` behavior but the implementation was never updated (or vice-versa). |
| **Recommendation** | Either (a) replace `HttpResponse(data, ...)` with `FileResponse(open(file_path, "rb"), content_type="image/jpeg")` to stream, matching the docstring (requires importing `FileResponse` at listings.py:20), or (b) update the docstring to say "reads the file into memory and returns `HttpResponse`." |
| **Effort** | Trivial |
| **Priority** | Recommended |

**Evidence — `src/backend/apps/ads/views/listings.py:100-117`**:
```python
def _serve_image(image_key: str) -> HttpResponse:
    """Serve a media file directly (development fallback without nginx.

    Uses ``FileResponse`` to stream the file from ``MEDIA_ROOT``.  In production,
    the ``media_gate`` view returns an ``X-Accel-Redirect`` header that nginx
    intercepts; this helper is only used when ``DEBUG=True``.
    """
    ...
    with open(file_path, "rb") as f:
        data = f.read()           # ← entire file in memory
    return HttpResponse(data, content_type="image/jpeg")  # ← not FileResponse
```

---

> **Validation:** ✅ **Validated — BEST-PRACTICE (no change).** Confirmed by source inspection. The dead code block is a true no-op.
>
> **Evidence surveyed:**
> - `sweep_orphaned_media.py:51-53` — `if rel_dir == ".": if _SEED_SUBDIR in os.listdir(media_root): pass` — the inner block only contains `pass`, performs no action, and makes no decision that affects flow.
> - `sweep_orphaned_media.py:55-56` — the actual seed exclusion: `if rel_dir == _SEED_SUBDIR or rel_dir.startswith(f"{_SEED_SUBDIR}/"): continue` — when `rel_dir == "."` (top-level), this condition is `False` (since `"." != "seed"` and `"."` doesn't start with `"seed/"`), so top-level files are correctly included. Seed files under `seed/` are excluded by the `rel_dir == _SEED_SUBDIR` check.

#### LOW-003: [LOW] — Dead code in `_walk_media_files`

| Field | Value |
|---|---|
| **ID** | LOW-003 |
| **Title** | Dead code in `_walk_media_files` |
| **Severity** | LOW |
| **File(s)** | `src/backend/apps/media/management/commands/sweep_orphaned_media.py:46-60` |
| **Status** | Open |
| **Validation Type** | BEST-PRACTICE |
| **Problem** | Lines 51-53 contain a dead code block: `if rel_dir == ".": if _SEED_SUBDIR in os.listdir(media_root): pass`. The inner block only contains `pass` — it performs no action and does not affect control flow. The seed directory exclusion is actually handled at lines 55-56: `if rel_dir == _SEED_SUBDIR or rel_dir.startswith(f"{_SEED_SUBDIR}/"): continue`. The dead block is confusing for maintainers and suggests incomplete refactoring. |
| **Impact** | Code clarity and maintainability. No functional impact. No behavioral risk. |
| **Root Cause** | An incomplete refactoring left a no-op check where the seed-exclusion logic was intended to go. |
| **Recommendation** | Remove the dead `if rel_dir == "."` block (lines 51-53). |
| **Effort** | Trivial |
| **Priority** | Recommended |

**Evidence — `src/backend/apps/media/management/commands/sweep_orphaned_media.py:51-56`**:
```python
    for dirpath, _dirnames, filenames in os.walk(media_root):
        rel_dir = os.path.relpath(dirpath, media_root)
        if rel_dir == ".":                      # ← dead block (line 51-53)
            if _SEED_SUBDIR in os.listdir(media_root):
                pass  # not in the top-level dir, handled below
        # Skip seed directory (and any subdir starting with seed/)  (line 55)
        if rel_dir == _SEED_SUBDIR or rel_dir.startswith(f"{_SEED_SUBDIR}/"):
            continue                            # ← actual seed exclusion (line 56)
```

---

> **Validation:** ✅ **Validated — BEST-PRACTICE (no change).** Confirmed by source inspection and grep. `media_gate` uses no cache decorators, no `cache_control()`, no `Vary` headers. Other public views were confirmed to use `never_cache`.
>
> **Evidence surveyed:**
> - `listings.py:120-198` — `media_gate` returns either `HttpResponse()` with `X-Accel-Redirect` (production, lines 183-185, 196-198) or `_serve_image()` (development, lines 182, 194). Neither path sets `Cache-Control`, `ETag`, or `Last-Modified`.
> - `ads/urls.py:25` — `path("media/<path:image_key>", media_gate, name="media_gate")` — registered without any decorator.
> - Grep for `never_cache` / `cache_control` / `Cache-Control` across `src/backend/` confirmed `never_cache` only on `logout.py:16`, `consent.py:277`, `consent.py:360`, `preferred_city.py:26`. `media_gate` uses none.
> - `models.py:522-525` — AdImage docstring: "UUID v4 + .jpg, no ad_id/user/telegram PII" — confirms keys are immutable and PII-free, making them safe for long-term caching.
> - `db-retention.md:102` — "UUID v4-based and immutable (confirmed in AdImage model)" — the finding's spec reference confirms immutability.

> **Nuance on recommendation:** The `media_gate` view performs a **DB lookup + ad-status check** on every request (listings.py:169-190). If a long `Cache-Control: max-age=31536000` is set on the response, a reverse proxy or browser cache could serve the response (including the X-Accel-Redirect or file bytes) without re-validating ad status. For a classifieds board where moderation rejection should immediately hide images, this is a consideration. The safest production policy is a moderate `max-age` (e.g. 1 hour) with a `Vary: Authorization` header, or a shorter immutable cache. The finding's recommendation of `max-age=31536000, immutable` is appropriate only if the image file itself is guaranteed to be deleted promptly on ad status change (via sweep or cascade signals). This is an implementation nuance, not a validation concern — the finding (missing cache headers) is valid.

#### LOW-004: [LOW] — No cache-control headers on `media_gate` responses

| Field | Value |
|---|---|
| **ID** | LOW-004 |
| **Title** | No cache-control headers on `media_gate` responses |
| **Severity** | LOW |
| **File(s)** | `src/backend/apps/ads/views/listings.py:120-198` |
| **Spec reference** | `docs/02-database/db-retention.md:102` (describes immutable storage keys) |
| **Status** | Open |
| **Validation Type** | BEST-PRACTICE |
| **Problem** | The `media_gate` view does not set any cache headers on its responses (no `Cache-Control`, `ETag`, or `Last-Modified`). It neither uses the `never_cache` decorator nor sets explicit caching directives. All other public views use `never_cache` (`logout.py:16`, `consent.py:277,360`, `preferred_city.py:26`). Since image storage keys are UUID v4-based and immutable (AdImage model: "UUID v4 + .jpg, no ad_id/user/telegram PII"), images are excellent candidates for browser/CDN caching. Without explicit headers, caching behavior is inconsistent or undefined. |
| **Impact** | Inconsistent caching behavior. Missed performance opportunity — every image request hits the Django process (DB lookup + ad-status check) even for immutable assets. |
| **Root Cause** | `media_gate` was likely treated as a dynamic view (like other `never_cache` pages) but its UUID-keyed assets are actually immutable, warranting long-term caching. |
| **Recommendation** | Add `Cache-Control: public, max-age=31536000, immutable` for production (`X-Accel-Redirect`) responses, since UUID keys are immutable. For the development fallback (`_serve_image`), add `no-cache` headers. Consider `Vary: Authorization` if staff vs non-staff responses differ (they do — staff bypass the PUBLISHED check). |
| **Effort** | Small |
| **Priority** | Recommended |

**Evidence — `src/backend/apps/ads/views/listings.py:180-198`** *(no cache headers set)*:
```python
    # Staff users (moderators/admins) can view any image regardless of status
    if request.user.is_staff:
        if settings.DEBUG:
            return _serve_image(image_key)
        response = HttpResponse()
        response["X-Accel-Redirect"] = f"/protected-media/{image_key}"
        return response   # ← no Cache-Control, no ETag

    ...

    if settings.DEBUG:
        return _serve_image(image_key)   # ← no cache headers

    response = HttpResponse()
    response["X-Accel-Redirect"] = f"/protected-media/{image_key}"
    return response   # ← no Cache-Control, no ETag
```

**Evidence — contrast: other public views use `never_cache`**:
```python
# logout.py:16
@never_cache

# consent.py:277, 360
@never_cache

# preferred_city.py:26
@never_cache
```

---

## Cross-Finding Analysis

### Cross-phase findings

| ID | Phase 05 ID | Root cause | Decision |
|----|-------------|------------|----------|
| MED-004 | AD-004 | `db-retention.md` says DRAFT retention = 7 days; code + phase spec = 30 min | Reclassified to DOC-UPDATE (LOW), matching Phase 05 AD-004 |

**MED-004 ≡ AD-004 (cross-phase).** Both findings identify the identical root cause: `db-retention.md:32,82` states DRAFT retention as "7 days", while `sweep_drafts.py:45` implements `timedelta(minutes=30)`, and the phase spec (`technical-specification.md:152`, `seller-stories.md:39`, Phase 05 spec `05-audit-ad-lifecycle.md:73`) all define 30 minutes. Phase 05 already validated this as `DOC-UPDATE` (code correct, doc outdated) with LOW severity. This report defers to that decision and reclassifies MED-004 accordingly. No merger is performed because the findings live in separate phase reports; the cross-phase reference is documented inline.

### Within-phase related findings

- **CR-001 ↔ MED-001:** Both touch the `cmd_cancel` → `delete_draft` cleanup path. CR-001 is the primary data-loss bug (original files destroyed after submit); MED-001 is the secondary inconsistency (`delete_draft` skips thumbnails). Fixing CR-001 (guard `cmd_cancel` against non-DRAFT ads) would make MED-001's `delete_draft` loop unreachable for the cancel-after-submit scenario, but MED-001 remains valid as a code-consistency issue (every other deletion path uses `storage_keys()`). **Not merged** — distinct root causes (CR-001: missing state-clear + missing guard; MED-001: wrong method call).
- **HIGH-001 ↔ HIGH-002:** Both are file-cleanup gaps. HIGH-001 is the absence of a model-level safety net (cascade-delete orphans files); HIGH-002 is the orphan sweep's race condition (deletes in-flight uploads). HIGH-002 is the backstop for HIGH-001, but the backstop itself is flawed. **Not merged** — different attack surfaces (model-level deletion vs. sweep-level cleanup).
- **HIGH-001 fix dependency:** Adding a `post_delete`/`pre_delete` signal on `AdImage` must respect the project's TX-then-FS pattern (files deleted after transaction commit, not inside it). A naive signal that calls `delete_photo()` directly inside the transaction would create the anti-pattern the project avoids. The fix should use `transaction.on_commit()`. This does **not** conflict with the sweep commands (which collect keys before the transaction and delete after commit) — double deletion is handled gracefully by `delete_photo`'s `FileNotFoundError` terminal case (filesystem.py:153-155).

### Conflicting evidence

None within this phase. All findings were independently verified against the live source tree and are consistent with each other.

### Dependency chains

| Finding | Depends on | Rationale |
|---------|-----------|-----------|
| CR-001 | — | Standalone fix: add `state.clear()` on success + guard `cmd_cancel` |
| HIGH-001 | — | Standalone fix: add model-level signal/override with `on_commit` |
| HIGH-002 | — | Standalone fix: staging dir or pending-upload registry |
| MED-001 | CR-001 | Low-impact: fixing CR-001 makes `delete_draft` unreachable for the cancel-after-submit path; MED-001 still warrants fixing independently |
| MED-002 | HIGH-002 | Related: a staging-directory fix for HIGH-002 would also improve MED-002 (files only enter permanent storage after validation) |
| MED-003 | — | Standalone fix: add DB indexes + migration |
| MED-004 | — | Doc-only fix |
| LOW-001 | — | Standalone fix: pop `icc_profile` |
| LOW-002 | — | Standalone fix: docstring or code |
| LOW-003 | — | Standalone fix: remove dead block |
| LOW-004 | — | Standalone fix: add cache headers (careful: consider moderation visibility) |

---

## Execution Validation

- **Targets still exist:** All cited files and line ranges are present and unchanged: `ad_create.py` (cmd_cancel at 105-123, process_preview at 782-856, delete_draft at 875-896, process_photos at 663-715), `models.py` (AdImage at 521-686, Meta at 597-620, storage_keys at 672), `listings.py` (_serve_image 100-117, media_gate 120-198), `filesystem.py` (strip_photo_exif 193-211, validate_photo 75-118, delete_photo 130-170), `sweep_orphaned_media.py` (46-60, 88-92), `sweep_drafts.py` (45), `submission.py` (158-179), `auto_moderation.py` (94-170), `deletion.py` (165-221), `consent_hard_delete.py` (69-93). ✅
- **Dependencies remain valid:** `AdStatus` enum unchanged; `AdImage.storage_keys()` unchanged; `PhotoSize.file_size` attribute available in aiogram 3.x; `assert_storage_key_contained()` unchanged; `delete_photo()` handles `FileNotFoundError` gracefully. ✅
- **No schema changes required** (except MED-003's additive index, which is backward-compatible). ✅
- **Plan is current:** This validation targets the Phase 99 validate task and the `findings.md` produced by the Phase 07 audit; no architectural drift observed between audit and validation. ✅

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 10 | CR-001, HIGH-001, HIGH-002, MED-001, MED-002, MED-003, LOW-001, LOW-002, LOW-003, LOW-004 |
| Reclassified | 1 | MED-004: severity MEDIUM→LOW, type SPEC-DEVIATION→DOC-UPDATE |
| Merged | 0 | (cross-phase: MED-004 ≡ AD-004 — documented inline, not merged into separate file) |
| Rejected | 0 | — |

### Rejected Findings

_None._ All 11 findings were verified against the live source tree, spec documents, and (where applicable) test code. Every finding remains applicable. No findings were stale, speculative, or lacked clear benefit.

### Reclassified Findings

| ID | Original Severity | New Severity | Original Type | New Type | Rationale |
|----|-------------------|-------------|---------------|----------|-----------|
| MED-004 | MEDIUM | LOW | SPEC-DEVIATION | DOC-UPDATE | Cross-phase duplicate of Phase 05 AD-004. The 30-minute implementation matches the phase spec (`technical-specification.md:152`, `seller-stories.md:39`, Phase 05 spec) and is the intended behavior (bounds orphaned-photo exposure from crashed FSM). Only `db-retention.md` is outdated. Reclassifying to DOC-UPDATE maintains cross-phase consistency; severity lowered from MEDIUM to LOW (doc-only fix). |

### Merged Findings

_None within phase 07._ The only cross-phase overlap is MED-004 ≡ AD-004 (Phase 05), which is documented inline on the MED-004 finding and in the Cross-Finding Analysis section above. The findings remain in their respective phase reports rather than being merged.

| Original ID | Cross-phase target | Rationale for *not* merging into same file |
|-------------|--------------------|-------------------------------------------|
| MED-004 | AD-004 (Phase 05) | Separate phase reports; AD-004 already validated as DOC-UPDATE. MED-004 deferred to that decision, not duplicated. |

---

## Rollout Analysis

| ID | Risk | Backward-compatible? | Test gap (must cover) | Validated? |
|----|------|----------------------|-----------------------|------------|
| CR-001 | High | No (behavior change: cancel after submit no longer destroys submitted ad media) | Add a regression test: submit ad → type "cancel" → assert original files + thumbnails still exist and DB rows intact | ✅ |
| HIGH-001 | Low | Yes (additive signal; must use `on_commit` for TX-then-FS) | Test: hard-delete an ad via ORM cascade → assert physical files are deleted after commit; test: file deletion failure does not block DB cascade | ✅ |
| HIGH-002 | Medium | No (upload flow change: staging dir) | Test: upload in-flight file → run orphan sweep → assert file survives; test: successful submit moves file from staging to permanent | ✅ |
| MED-001 | Low | Yes (drop-in `storage_keys()` replacement) | Test: `delete_draft` on a DRAFT ad with AdImage rows + thumbnails → assert all keys deleted via `delete_photo` | ✅ |
| MED-002 | Low | Yes (pre-check is additive; must handle `file_size=None`) | Test: `PhotoSize` with `file_size > 2MB` → assert `download_photo` not called; test: `file_size=None` → falls through to download+validate | ✅ |
| MED-003 | Low | Yes (additive index) | Migration test; `test_media_security.py` covers the query pattern already | ✅ |
| MED-004 | None | Yes (doc-only) | N/A | ✅ |
| LOW-001 | Low | Yes (additive `icc_profile` pop) | Test: `strip_photo_exif` on JPEG with embedded ICC profile → assert output has no `icc_profile` | ✅ |
| LOW-002 | None | Yes (doc fix or `FileResponse` swap) | If using `FileResponse`: test streaming + import | ✅ |
| LOW-003 | None | Yes (dead code removal) | No test gap — covered by `sweep_orphaned_media` dry-run tests | ✅ |
| LOW-004 | Low | Yes (additive headers) | Test: `media_gate` response includes `Cache-Control: max-age=31536000, immutable` for production; `no-cache` for dev | ✅ |

### Rollout safety issues detected

1. **HIGH-001 signal + TX-then-FS tension (medium rollout risk):** Adding a `post_delete` signal on `AdImage` that calls `delete_photo()` directly would violate the project's TX-then-FS pattern — filesystem deletions inside `transaction.atomic()` cannot be rolled back. If a rollback occurs after file deletion, DB rows are orphaned pointing to deleted files. The correct implementation must use `transaction.on_commit()` in the signal handler, so files are only deleted after the DB transaction commits. The sweep commands already do this correctly (collect keys before TX, delete after TX). The signal must match this pattern. **Not a blocker** — just a design constraint on the fix.

2. **CR-001 + MED-001 joint fix ordering (low rollout risk):** CR-001's fix (guard `cmd_cancel` against non-DRAFT ads) makes `delete_draft` unreachable in the cancel-after-submit scenario. MED-001's fix (use `storage_keys()` in `delete_draft`) should be applied first or together — otherwise the window between fixes still leaves the thumbnail-orphan gap. They should ship as a single change set for the cancel flow.

3. **LOW-004 moderation visibility (validator advisory):** Setting `Cache-Control: max-age=31536000, immutable` on `media_gate` responses means a reverse proxy or browser may cache the response (including X-Accel-Redirect or file bytes) without re-checking ad status. If an ad is rejected/deleted and its image should stop being served, the cached response could serve a stale image for up to 1 year. Recommendation: use a moderate `max-age` (e.g. 3600) with revalidation, or ensure the image file is deleted promptly on status change (via HIGH-001's signal fix). Not a blocker for the LOW-004 fix — just a policy detail.

### Circular / hidden dependencies

_None._ All 11 findings are independently fixable. The only coupling is CR-001 ↔
MED-001 (both in the cancel flow), which should ship together. No fragile
insertion points detected beyond the TX-then-FS signal constraint noted above.

---

## Warnings

- **HIGH-001 + HIGH-002 (file cleanup surface):** Two independent mechanisms
  (model-level signal vs. orphan sweep) will eventually both delete files. The
  orphan sweep deletes by key-not-in-AdImage; the model signal deletes on
  AdImage deletion. Both call `delete_photo()`, which gracefully handles
  `FileNotFoundError` (filesystem.py:153-155) — so double-deletion is safe. No
  conflict, but worth noting for future maintainers.

- **HIGH-002 mitigation scope creep risk:** The finding recommends a staging
  directory approach. This would require changes to `save_photo`, `delete_photo`,
  `sweep_orphaned_media` (exclude staging), and `submission.py` (move files on
  submit). This touches the core upload path — ensure tests cover the
  staging→permanent transition under both success and failure.

- **MED-002 `file_size` reliability:** Telegram reports `file_size` on
  `PhotoSize` objects, but it is `Optional[int]`. A `None` value must fall
  through to download+validate. Additionally, `file_size` is a
  Telegram-reported value, not a security boundary — the post-download
  `validate_photo` size check must remain as defense-in-depth.

- **LOW-002 `FileResponse` vs `HttpResponse`:** If the team chooses to align
  code with the docstring (use `FileResponse`), the `_serve_image` return type
  annotation `-> HttpResponse` is still correct (`FileResponse` subclasses
  `HttpResponse`), but the import at `listings.py:20` must be updated. If the
  team chooses to align the docstring with the code, no import change is needed.

- **Executive summary miscount:** The original findings file's executive summary
  says "3 LOW" but the summary table lists 4 LOW findings (LOW-001 through
  LOW-004). This is a minor doc inconsistency in the original report, not a
  finding validity issue.

---

## Required Fixes

1. **CR-001 (CRITICAL, SPEC-DEVIATION):** In `process_preview` (ad_create.py),
   add `await state.clear()` immediately after the success-path
   `message.answer()` at line 841. In `cmd_cancel` (ad_create.py:105-123),
   before deleting photos from FSM state, fetch the Ad by `ad_id` and check its
   status — skip photo deletion if the ad is no longer DRAFT. Add a regression
   test: submit an ad (on-moderation or published), then type "cancel" — assert
   original files + thumbnails on disk and `AdImage` rows are intact.

2. **HIGH-001 (HIGH, SPEC-DEVIATION):** Add a `pre_delete` signal on `AdImage`
   that collects `storage_keys()` and registers a `transaction.on_commit()`
   callback to call `delete_photo()` for each key — preserving the TX-then-FS
   pattern. The signal must be registered in `apps/media/apps.py` (or a new
   `signals.py`) and connected via `AppConfig.ready()`. Verify it does not
   conflict with the sweep commands (which collect keys before TX and delete
   after — double deletion is safe via `delete_photo`'s `FileNotFoundError`
   handling).

3. **HIGH-002 (HIGH, SPEC-DEVIATION):** Implement one of: (a) accept uploads
   into a `staging/` subdirectory excluded from `sweep_orphaned_media` and move
   to permanent storage on successful `submit_ad`; or (b) add a lightweight
   "pending uploads" registry (model or cache set) that `_collect_referenced_keys`
   also queries. The staging approach is preferred — it is the cleanest
   separation of concerns (in-progress files vs. committed files).

4. **MED-001 (MEDIUM, BEST-PRACTICE):** In `delete_draft` (ad_create.py:891-892),
   replace `delete_photo(img.image)` with iteration over `img.storage_keys()` to
   match every other deletion path.

5. **MED-002 (MEDIUM, BEST-PRACTICE):** In `process_photos` (ad_create.py:663),
   check `photo.file_size` (Telegram `PhotoSize.file_size`) before
   `download_photo()`. If `file_size` exceeds the 2MB limit, reject immediately
   without downloading. If `file_size` is `None`, fall through to
   download+validate. Keep the post-download `validate_photo` as defense-in-depth.

6. **MED-003 (MEDIUM, BEST-PRACTICE):** Add `models.Index(...)` entries to
   `AdImage.Meta.indexes` for `image`, `thumbnail_small`, `thumbnail_medium`,
   and `thumbnail_large`. Generate and apply the migration. Run `test_media_security.py` to verify query correctness is unchanged.

7. **MED-004 (LOW, DOC-UPDATE):** Update `db-retention.md` line 32 and line 82
   to read "30 minutes" for DRAFT retention, replacing the incorrect "7 days".
   Add a brief note that the 30-minute window bounds orphaned-photo exposure
   from a crashed bot FSM. No code change. (Cross-phase: matches Phase 05 AD-004.)

8. **LOW-001 (LOW, BEST-PRACTICE):** In `strip_photo_exif` (filesystem.py:208),
   add `img.info.pop("icc_profile", None)` after the existing EXIF pop. Add a
   test in `TestExifStripping` asserting `icc_profile` is absent from output.

9. **LOW-002 (LOW, DOC-UPDATE):** Either (a) replace `HttpResponse(data, ...)`
   with `FileResponse(open(file_path, "rb"), content_type="image/jpeg")` in
   `_serve_image` (listings.py:115-117) and import `FileResponse` at line 20, or
   (b) update the docstring to accurately describe the `HttpResponse`
   read-into-memory behavior.

10. **LOW-003 (LOW, BEST-PRACTICE):** Remove the dead `if rel_dir == "."` block
    (sweep_orphaned_media.py:51-53) from `_walk_media_files`.

11. **LOW-004 (LOW, BEST-PRACTICE):** Add `Cache-Control: public, max-age=31536000,
    immutable` to `media_gate` production responses (X-Accel-Redirect path). For
    the `_serve_image` dev fallback, add `Cache-Control: no-cache` (image files
    are deleted from server on ad removal, so `no-cache` forces revalidation).
    Consider `Vary: Authorization` since staff bypass the PUBLISHED check.

---

## Advisory Recommendations

- **HIGH-001 signal design:** Consider a centralized `MediaDeletionService`
  that all deletion paths (sweeps + model signal) call, rather than each sweep
  command reimplementing the "collect keys before TX → delete after commit"
  pattern. This would reduce duplication across `sweep_drafts`, `delete_sweep`,
  `purge_failed_ads`, `purge_rejected_ads`, `purge_deleted_ads`,
  `consent_hard_delete`, and `soft_delete_user_ads`. Note: this is a larger
  refactor — only pursue if the codebase grows beyond 6 sweep commands.
- **HIGH-002 + MED-002 synergy:** The staging-directory approach for HIGH-002
  would also improve MED-002 — files only enter the permanent (sweeped)
  directory after successful validation + submission. Consider bundling these
  fixes.
- **CR-001 + MED-001 bundling:** Ship both fixes to the cancel flow together —
  they touch the same code paths and the combined change set is small.
- **LOW-004 staging compatibility:** If HIGH-002's staging directory is
  implemented, `_serve_image` and `media_gate` should also serve from the
  staging area for in-progress previews (currently `save_photo` writes to the
  permanent MEDIA_ROOT flat — thumbnails are not generated for in-flight uploads,
  so staging adds no serving complexity).

---

## Observations (from original findings, verified)

### Positive patterns already in place

- **TX-then-Filesystem:** `sweep_drafts.py:70-76` deletes DB rows inside
  `transaction.atomic()`, then deletes physical files after commit (lines 75-76,
  outside the `with transaction.atomic():` block). All six sweep commands
  (`delete_sweep`, `purge_failed_ads`, `purge_rejected_ads`, `purge_deleted_ads`,
  `consent_hard_delete`) and `soft_delete_user_ads` follow the same pattern. ✅
- **`storage_keys()` method:** `AdImage.storage_keys()` (models.py:672-686)
  returns all keys (image + thumbnails). Used correctly by `sweep_drafts`
  (line 66), `soft_delete_user_ads` (deletion.py:201), `consent_hard_delete`
  (line 75), `delete_sweep` (line 68), `purge_failed_ads` (line 67),
  `purge_rejected_ads` (line 67), and `purge_deleted_ads` (line 67). ✅
- **Path traversal defense:** `assert_storage_key_contained()` (filesystem.py:34-65)
  validates keys within MEDIA_ROOT via NUL-byte, absolute-path, `..`-segment, and
  `realpath` containment checks. `test_media_security.py:376-435` verifies
  `../`, URL-encoded traversal, NUL bytes, and absolute paths. ✅
- **Seed exclusion:** `sweep_orphaned_media` correctly excludes `seed/`
  subdirectory (sweep_orphaned_media.py:55-56). ✅
- **Advisory locks:** All sweep commands use advisory locks
  (`AdvisoryLockId.SWEEP_ORPHANED_MEDIA`, `SWEEP_DRAFTS`, `DELETE_SWEEP`,
  `PURGE_FAILED_ADS`, `PURGE_REJECTED_ADS`, `PURGE_DELETED_ADS`,
  `CONSENT_HARD_DELETE`) for safe concurrent execution. ✅

### Inconsistencies (all findings validated above)

- `delete_draft` (ad_create.py:892) does NOT use `storage_keys()` while every
  other deletion path does → MED-001 (VALIDATED, BEST-PRACTICE).
- `cmd_cancel` (ad_create.py:116-117) only deletes from FSM `photos` list
  (originals only, not thumbnail keys) → part of CR-001 (VALIDATED,
  SPEC-DEVIATION) and MED-001 (VALIDATED, BEST-PRACTICE).
- `sweep_drafts.py:45` uses 30 minutes; `db-retention.md:32` says 7 days →
  MED-004 (VALIDATED, DOC-UPDATE, cross-phase with AD-004).
