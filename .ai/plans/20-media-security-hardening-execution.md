# Media Security Hardening — Execution Plan (Phase 07, Remaining Work)

**Plan ID:** `20-media-security-hardening-execution`  
**Source:** `.ai/audit/99-validation/07-media-validated-findings.md` (validated 2026-09-05)  
**Companion code context:** `.ai/plans/code-context-media-07.md`  
**Status:** 4 remaining findings (ME-002 5-of-7 sweeps, ME-004, ME-005, ME-006)  

---

## 1. Baseline — What Is Already Done

The following were committed in a prior cycle (verified against the working tree):

| Item | Location | Evidence |
|---|---|---|
| ENT-001 — `delete_photo` relocated | `apps/media/services/filesystem.py` | All 7 import sites now `from apps.media.services.filesystem import delete_photo` |
| ME-001 — containment check | `filesystem.py` (`assert_storage_key_contained` called in `delete_photo`) | RegexValidator + 4 CheckConstraints on `AdImage` model fields; `save()` guard in place; serving path (`media_gate`/`_serve_image`) hardened |
| NEW-ME-007 — enum IDs | `core/enums.py` (`SWEEP_ORPHANED_MEDIA = 103`, `CATALOG_LOAD = 104`) | Scheduler line in `entrypoint-scheduler.sh` line 33; lock-structure tests + CI AST assertion tests in place; `sweep_orphaned_media.py` routes through `delete_photo` |
| ME-003-secondary — escalation | `media/models.py` (`MediaDeletionError` model); `filesystem.py` (`_record_deletion_error()`) | Called from `delete_photo` exhausted-retry path |
| ME-002 (2/7) — `storage_keys()` | `ads/models.py` (`AdImage.storage_keys()` at ~line 672) | `consent_hard_delete.py` and `deletion.py` already use it; regression test + 5 unit tests exist |

---

## 2. Remaining Work Summary

| # | Finding | Severity | Scope | Agent needed |
|---|---------|----------|-------|--------------|
| 1 | ME-002 (5 sweeps) | HIGH | Replace `values_list("image", flat=True)` with `img.storage_keys()` in 5 management commands | None — pattern established by `consent_hard_delete.py` |
| 2 | ME-004 | HIGH | Add `len(photos) >= 5` cap before `download_photo`; fix inverted error message in `process_photos` | None — straightforward logic change |
| 3 | ME-006 | HIGH | Wire `check_upload_rate_limit(user_id)` into `process_photos` before `download_photo` | None — pattern established by `contact.py` |
| 4 | ME-005 | MEDIUM | Set `Image.MAX_IMAGE_PIXELS` in `MediaConfig.ready()` | None — one-line in `ready()` |

**Key constraint: ME-004 and ME-006 both insert code at the same anchor in `process_photos` (before `download_photo`). They must be applied sequentially in the same PR — ME-006 depends on ME-004 being applied first so the anchor remains unambiguous.**

---

## 3. Dependency DAG

```
ME-001 (done) ──┬──> ME-002 (5 sweeps) ──> test_sweep_commands.py
                └──> (containment check already in delete_photo)

ME-004 ──> ME-006    (same PR; ME-006 inserts after ME-004's count cap)
                └──> test_ad_create.py (process_photos tests)

ME-005              (fully independent)
                └──> test_media_config.py (unit test)
```

**Parallel-safe pairs:**
- ME-002 (backend) ∥ ME-004 (bot handler) — no shared files
- ME-002 (backend) ∥ ME-005 (backend app config) — no shared files
- ME-005 (backend app config) ∥ ME-004 (bot handler) — no shared files
- ME-005 (backend app config) ∥ ME-006 (bot handler) — no shared files

**NOT parallel-safe:**
- ME-004 ∦ ME-006 — same function, same insertion anchor

---

## 4. Execution Blocks

<!-- TASK_START: me002_complete_thumbnail_migration -->

### Block 1: ME-002 — Complete thumbnail-key migration in 5 remaining sweep commands

```yaml
id: me002_remaining_sweeps
title: "ME-002: Migrate 5 sweep commands to use AdImage.storage_keys()"
source_reference: .ai/plans/20-media-security-hardening-execution.md
source_section: "Block 1: ME-002"
priority: high
depends_on: []   # ME-001 containment already done (verified in working tree)
classification: mandatory
risk: low          # mechanical pattern replacement; ME-001 containment already guards delete_photo
replaces_pattern: "AdImage.objects.filter(ad_id__in=ad_ids).values_list('image', flat=True)"
```

**Description:**
Five management commands still collect only the main `image` key via `values_list("image", flat=True)` instead of calling `AdImage.storage_keys()`. This leaves thumbnail files (`thumbnail_small`, `thumbnail_medium`, `thumbnail_large`) orphaned on disk after sweep execution. Two commands (`consent_hard_delete.py`, `deletion.py`) were already migrated in the prior cycle; this block completes the migration for the remaining five.

**Already implemented reference (do not change):**
- `consent_hard_delete.py` lines 71–75 — uses `img.storage_keys()` list comprehension
- `deletion.py` lines 204–208 — uses `img.storage_keys()` list comprehension

**Implementation scope (5 files, identical transformation each):**

For each command, replace the storage-key collection block inside `handle()`:

```
OLD:
    storage_keys = list(
        AdImage.objects.filter(ad_id__in=ad_ids).values_list(
            "image", flat=True
        )
    )

NEW:
    storage_keys = [
        key
        for img in AdImage.objects.filter(ad_id__in=ad_ids)
        for key in img.storage_keys()
    ]
```

| File | Function | Anchor |
|---|---|---|
| `apps/core/management/commands/delete_sweep.py` | `Command.handle` | `ad image keys are collected before ORM cascade` comment block → `values_list("image", flat=True)` call |
| `apps/core/management/commands/purge_deleted_ads.py` | `Command.handle` | same pattern |
| `apps/core/management/commands/purge_rejected_ads.py` | `Command.handle` | same pattern |
| `apps/core/management/commands/purge_failed_ads.py` | `Command.handle` | same pattern |
| `apps/core/management/commands/sweep_drafts.py` | `Command.handle` | same pattern |

Each command already imports `AdImage` (from `apps.ads.models`) and `delete_photo` (from `apps.media.services.filesystem`). No import changes needed — `storage_keys()` is a model method.

**Acceptance criteria:**
1. All five `handle()` methods call `img.storage_keys()` instead of `values_list("image", flat=True)`
2. The `AdImage` import is already present in each file (verified — no new imports needed)
3. `ruff check` passes on all modified files
4. All existing sweep tests still pass
5. New regression tests verify thumbnail keys are passed to `delete_photo`

**Tests to add (in `test_sweep_commands.py`):**

Following the established pattern of `TestConsentHardDelete.test_collects_thumbnail_keys_for_media_cleanup` (line 318), add one regression test to each sweep test class:

| Test class | New test method | Ad status/date to trigger |
|---|---|---|
| `TestDeleteSweep` | `test_collects_thumbnail_keys_for_media_cleanup` | `ARCHIVED`, `published_at` = 200 days ago |
| `TestPurgeDeletedAds` | `test_collects_thumbnail_keys_for_media_cleanup` | `DELETED`, `deleted_at` = 200 days ago |
| `TestPurgeRejectedAds` | `test_collects_thumbnail_keys_for_media_cleanup` | `REJECTED`, `rejected_at` = 120 days ago |
| `TestPurgeFailedAds` | `test_collects_thumbnail_keys_for_media_cleanup` | `ON_MODERATION_FAILED`, `moderation_failed_at` = 10 days ago |
| `TestSweepDrafts` | `test_collects_thumbnail_keys_for_media_cleanup` | `DRAFT`, `created_at` = 90 minutes ago |

Each test follows the identical structure:
```python
def test_collects_thumbnail_keys_for_media_cleanup(self, seller, category, city, monkeypatch):
    # 1. Create expired ad in the correct status
    # 2. Create AdImage with image + all 3 thumbnail fields populated
    # 3. monkeypatch delete_photo on the command module to record keys
    # 4. call_command(...)
    # 5. assert sorted(deleted_keys) == sorted(img.storage_keys())
    # 6. assert Ad removed from DB
```

**Run command:**
```powershell
$dc run --rm -e PYTEST_OPTS="-k 'test_collects_thumbnail_keys_for_media_cleanup or TestDeleteSweep or TestPurgeDeletedAds or TestPurgeRejectedAds or TestPurgeFailedAds or TestSweepDrafts'" test
```

<!-- TASK_END: me002_remaining_sweeps -->

---

<!-- TASK_START: me004_count_cap -->

### Block 2: ME-004 — Enforce upload count cap + fix inverted error message in `process_photos`

```yaml
id: me004_count_cap
title: "ME-004: Enforce 5-photo upload cap at the edge + fix inverted error message"
source_reference: .ai/plans/20-media-security-hardening-execution.md
source_section: "Block 2: ME-004"
priority: high
depends_on: []
classification: mandatory
risk: low          # adds a guard clause; no change to happy-path behavior for <=5 photos
```

**Description:**
`process_photos` in `ad_create.py` appends each uploaded photo to FSM state unconditionally after downloading and saving it (line 708). The only 1–5 enforcement is `PhotoCountPayload(photo_count=count)` which fires on the "done" command — after all photos are already on disk. Two problems:
1. No cap before `download_photo` → unbounded uploads waste disk/CPU, and photos beyond the 5th become orphans (no AdImage row created).
2. The "done" error message says "Please send at least 1 photo (you have N)" when the actual failure is N > 5 (inverted text).

**Implementation scope (1 file):**

`src/telegram_bot/handlers/ad_create.py` — `process_photos` function (lines 646–720):

1. **Insert count-cap guard before `download_photo` (before line 686):**

```python
    # Enforce the hard cap before downloading — prevents unbounded uploads
    # and orphaned files beyond the 5-photo limit.
    if len(photos) >= 5:
        await message.answer(
            f"You already have {len(photos)} photos. "
            "You can upload at most 5 photos."
        )
        return
```

Insert point: anchored after the `photo = message.photo[-1]` block (line 682) and before the `# Download photo bytes for validation` comment (line 684).

2. **Fix the inverted error message in the "done" handler (line 663):**

Replace:
```python
            await message.answer(f"Please send at least 1 photo (you have {count}).")
```

With context-aware messaging:
```python
            if count == 0:
                await message.answer("Please send at least 1 photo before finishing.")
            else:
                await message.answer(
                    f"You can upload at most 5 photos (you have {count})."
                )
```

This keeps `PhotoCountPayload` as the validation gate (its `ge=1, le=5` constraint still raises `ValidationError`) but surfaces the correct user-facing message for each failure case.

**Acceptance criteria:**
1. `len(photos) >= 5` check rejects before `download_photo` is called
2. The "done" handler shows the correct error message for both `count == 0` and `count > 5`
3. The happy path (1–5 photos) is unchanged
4. `ruff check` passes on the modified file
5. New tests verify the cap and the fixed message

**Tests to add (in `src/telegram_bot/tests/test_ad_create.py`):**

| Test | Description |
|---|---|
| `test_process_photos_rejects_after_five` | 5 photos in state + new photo → `message.answer` called with cap message, `download_photo` NOT called |
| `test_done_with_zero_photos_shows_correct_message` | Empty `photos` list + "done" → message says "at least 1" |
| `test_done_with_six_photos_shows_correct_message` | 6 photos in state + "done" → message says "at most 5", NOT "at least 1" |

These tests reuse the existing `_build_state` / `_build_message` helpers and follow the `TestProcessPreviewLanguageDetection` class pattern (async, mocked state, `pytest.mark.django_db(transaction=True)`).

**Run command:**
```powershell
$dc run --rm -e PYTEST_OPTS="-k 'test_process_photos_rejects_after_five or test_done_with'" test
```

<!-- TASK_END: me004_count_cap -->

---

<!-- TASK_START: me006_rate_limit -->

### Block 3: ME-006 — Wire `check_upload_rate_limit` into `process_photos`

```yaml
id: me006_rate_limit
title: "ME-006: Wire check_upload_rate_limit into process_photos"
source_reference: .ai/plans/20-media-security-hardening-execution.md
source_section: "Block 3: ME-006"
priority: high
depends_on:
  - me004_count_cap   # both insert before download_photo in the same function
classification: advisory
risk: low          # adds a guard clause; rate limiter already implemented, just uncalled
```

**Description:**
`check_upload_rate_limit` (rate_limit.py:30) implements an atomic `cache.add`/`cache.incr` sliding-window limiter (10 uploads / 60s, keyed by `bot_upload_rl:{user_id}`). It is defined but has **zero call sites** — grep confirms only the definition matches. The upload handler `process_photos` calls `validate_photo` and `save_photo` but never checks the rate limit, so a seller (or compromised bot client) can spam uploads unbounded.

The rate limiter is already correctly implemented; it just needs to be wired into the upload entry point. The reference pattern is `contact.py` (line 20 import, line 118 call).

**Implementation scope (1 file):**

`src/telegram_bot/handlers/ad_create.py` — `process_photos` function (lines 646–720):

1. **Add import** — after the existing `from telegram_bot.schemas.message_payloads import (...)` block (line 54), add:

```python
from telegram_bot.services.rate_limit import check_upload_rate_limit
```

2. **Insert rate-limit check before `download_photo`** — after ME-004's count-cap guard (once ME-004 is applied), insert:

```python
    # Enforce per-seller upload burst limit (anti-abuse).
    user_id = data.get("user_id")
    if user_id is not None and not check_upload_rate_limit(user_id):
        await message.answer(
            "Uploading too fast, please wait a moment."
        )
        return
```

Insert point: anchored after ME-004's count-cap guard and before the `# Download photo bytes for validation` comment. The `user_id` is available via `data = await state.get_data()` (line 650) — it is set by `cmd_post` at FSM initiation (line 117: `ad = await create_draft_ad(user_id=data["user_id"])`).

**Acceptance criteria:**
1. `check_upload_rate_limit` is imported in `ad_create.py`
2. `process_photos` calls `check_upload_rate_limit(data["user_id"])` before `download_photo`
3. When `check_upload_rate_limit` returns `False`, `message.answer` is called with the rate-limited message and `download_photo` is NOT called
4. When it returns `True`, the flow proceeds to `download_photo` as before
5. `ruff check` passes on the modified file
6. New test verifies the False path

**Tests to add (in `src/telegram_bot/tests/test_ad_create.py`):**

| Test | Description |
|---|---|
| `test_process_photos_rate_limited` | Mock `check_upload_rate_limit` → `False`; assert `message.answer` called with rate-limit message, `download_photo` NOT called |
| `test_process_photos_allows_when_not_rate_limited` | Mock `check_upload_rate_limit` → `True`; assert flow proceeds past the rate-limit check |

Follow the existing test pattern: monkeypatch `check_upload_rate_limit` in `telegram_bot.handlers.ad_create`, use `_build_state` with `user_id` set, mock the message + photo.

**Run command:**
```powershell
$dc run --rm -e PYTEST_OPTS="-k 'test_process_photos_rate_limited or test_process_photos_allows'" test
```

<!-- TASK_END: me006_rate_limit -->

---

<!-- TASK_START: me005_max_image_pixels -->

### Block 4: ME-005 — Set `Image.MAX_IMAGE_PIXELS` project-wide

```yaml
id: me005_max_image_pixels
title: "ME-005: Set Image.MAX_IMAGE_PIXELS in MediaConfig.ready()"
source_reference: .ai/plans/20-media-security-hardening-execution.md
source_section: "Block 4: ME-005"
priority: medium
depends_on: []
classification: advisory
risk: low          # sets a PIL global; valid images (max 2560²) are unaffected
```

**Description:**
`validate_photo` (in `apps/media/services/filesystem.py`) enforces a 2MB byte-size cap, then calls `Image.open()` + `ImageOps.exif_transpose()` which triggers a full pixel decode **before** the dimension check. Pillow's library default `MAX_IMAGE_PIXELS` (~89M) allows a 10000×10000 image (100M pixels) to fully decode into ~300MB with only a silent `DecompressionBombWarning`. The project never sets `Image.MAX_IMAGE_PIXELS` — grep across all of `src/` returns zero matches.

Setting it in `MediaConfig.ready()` ensures it applies to both processes (web + bot) since both call `django.setup()` which triggers app `ready()`.

**Implementation scope (1 file):**

`src/backend/apps/media/apps.py` — `MediaConfig` class:

```python
"""
Media app for photo thumbnail generation and media processing.
"""

from PIL import Image

from django.apps import AppConfig


class MediaConfig(AppConfig):
    name = "apps.media"
    verbose_name = "Media"

    def ready(self) -> None:
        """Set Pillow's decompression-bomb ceiling.

        Validates_photo enforces a 2MB byte cap and a 2560×2560 dimension cap,
        but ``Image.open()`` + ``ImageOps.exif_transpose()`` in validate_photo
        and strip_photo_exif trigger a full pixel decode *before* the dimension
        check. Setting MAX_IMAGE_PIXELS just above the 2560² ceiling ensures
        Pillow raises ``DecompressionBombError`` for oversized images instead
        of silently allocating ~300MB.
        """
        # 2560 × 2560 × 2 = 13,107,200 — twice the max allowed dimension area,
        # allowing a small safety margin above the 2560×2560 policy ceiling.
        Image.MAX_IMAGE_PIXELS = 2560 * 2560 * 2
```

**Acceptance criteria:**
1. `MediaConfig` has a `ready()` method that sets `Image.MAX_IMAGE_PIXELS`
2. The value is `2560 * 2560 * 2` (13,107,200 pixels) — just above the 2560² policy ceiling
3. `ruff check` passes on the modified file
4. Unit test verifies the constant is set

**Tests to add (new file: `apps/media/tests/test_media_config.py`):**

```python
"""Unit tests for MediaConfig.ready() — MAX_IMAGE_PIXELS setting."""

from PIL import Image
import pytest

pytestmark = [pytest.mark.unit]


def test_max_image_pixels_is_set() -> None:
    """MediaConfig.ready() sets MAX_IMAGE_PIXELS to twice the 2560² ceiling."""
    from apps.media.apps import MediaConfig

    config = MediaConfig("apps.media", "apps.media")
    config.ready()

    assert Image.MAX_IMAGE_PIXELS == 2560 * 2560 * 2
```

**Run command:**
```powershell
$dc run --rm -e PYTEST_OPTS="-k 'test_max_image_pixels_is_set'" test
```

<!-- TASK_END: me005_max_image_pixels -->

---

## 5. Rollout Sequence

| Step | Task | Parallel with | Notes |
|------|------|---------------|-------|
| 1 | **Block 1** (ME-002: 5 sweeps) | Block 4 (ME-005) | Backend-only; no bot handler changes. Safe to run concurrently. |
| 2 | **Block 4** (ME-005: MAX_IMAGE_PIXELS) | Block 1 (ME-002) | Single-file change in `apps/media/apps.py`. |
| 3 | **Block 2** (ME-004: count cap + message fix) | Blocks 1 & 4 | Bot handler change. Can run in parallel with backend blocks. |
| 4 | **Block 3** (ME-006: rate limit wiring) | — | Must run **after** Block 2 (same `process_photos` insertion anchor). Same PR as Block 2. |

**PR grouping recommendation:**
- **PR A:** Block 1 (ME-002: 5 sweeps) — backend, atomic, self-contained
- **PR B:** Blocks 2+3 (ME-004 + ME-006: upload hardening) — bot handler, same function
- **PR C:** Block 4 (ME-005: MAX_IMAGE_PIXELS) — backend, trivially independent

Alternatively, PR A and PR C can merge in parallel; PR B is independent of both.

---

## 6. Verification Matrix

| Block | Test file(s) | Test command | Marker |
|---|---|---|---|
| ME-002 | `apps/core/tests/test_sweep_commands.py` | `PYTEST_OPTS="-k 'test_collects_thumbnail_keys_for_media_cleanup'"` | `django_db integration slow` |
| ME-004 | `telegram_bot/tests/test_ad_create.py` | `PYTEST_OPTS="-k 'test_process_photos_rejects_after_five or test_done_with'"` | `django_db transaction=True slow integration concurrent` |
| ME-006 | `telegram_bot/tests/test_ad_create.py` | `PYTEST_OPTS="-k 'test_process_photos_rate_limited or test_process_photos_allows'"` | `django_db transaction=True slow integration concurrent` |
| ME-005 | `apps/media/tests/test_media_config.py` | `PYTEST_OPTS="-k 'test_max_image_pixels_is_set'"` | `unit` (no DB needed) |

**Global gate (after all blocks):**
```powershell
$dc run --rm test
```
> Full fast test suite (skips nightly `seed` suite ~300s), auto-starts test DB.

**Lint + typecheck:**
```powershell
uv run ruff check src/backend/apps/core/management/commands/ src/telegram_bot/handlers/ad_create.py src/backend/apps/media/apps.py
uv run ruff format --check src/backend/apps/core/management/commands/ src/telegram_bot/handlers/ad_create.py src/backend/apps/media/apps.py
uv run basedpyright src/telegram_bot/handlers/ad_create.py src/backend/apps/media/apps.py
```

---

## 7. Risk Assessment

| Block | Risk | Mitigation |
|---|---|---|
| ME-002 (5 sweeps) | Low — mechanical replacement; `delete_photo` containment (ME-001) already in place | All 5 sweeps already pass keys through `delete_photo`, which now has `assert_storage_key_contained()` |
| ME-004 (count cap) | Low — adds a guard clause before the existing download path | Existing happy path (1–5 photos) is unchanged; the cap only intercepts the N≥5 case |
| ME-006 (rate limit) | Low — rate limiter is fully implemented; just uncalled | `contact.py` demonstrates the exact pattern; cache fallback to `True` on `ValueError` |
| ME-005 (MAX_IMAGE_PIXELS) | Low — sets a PIL global just above the 2560² ceiling | Only affects images that would already be rejected by the dimension check; valid images are under the limit |

**No blocks require Auditor/Researcher/Planner agent intervention.** All four have established patterns in the codebase (consent_hard_delete.py for storage_keys, contact.py for rate-limit wiring, filesystem.py for PIL usage, and the sweep test suite for test patterns).

---

## 8. Post-Implementation: Remaining Advisory Item

**ME-003 (HIGH) — escalation to structured metric:** The `delete_photo` function logs exhausted-retry errors via `logger.error()` (filesystem.py, `_record_deletion_error()` already persists them to the `MediaDeletionError` model per the prior cycle). The remaining advisory step is to escalate these to an `AnalyticsEvent` for observability between hourly sweep windows. This is an advisory follow-up and is **not** in scope for the 4 execution blocks above.
