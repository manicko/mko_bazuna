# Code Context: Media Security Audit (Phase 07) — Current State

## Source plan
`.ai/audit/99-validation/07-media-validated-findings.md` (validated 2026-09-05) — 6 findings (ME-001–ME-006) + NEW-ME-007.

## Status snapshot (verified against working tree)

### DONE (already implemented and committed)

| Item | Location | Evidence |
|---|---|---|
| **ENT-001** — `delete_photo` relocated | `apps/media/services/filesystem.py` | 211 lines; `delete_photo` at l.130; `assert_storage_key_contained()` at l.34; `KEY_FORMAT_REGEX` at l.28; all 7 import sites now `from apps.media.services.filesystem import delete_photo` (delete_sweep, purge_*, sweep_drafts, consent_hard_delete, deletion.py, ad_create.py) |
| **ME-001** — containment check | `filesystem.py:146` | `assert_storage_key_contained(storage_key)` called before `os.remove` at l.150 |
| **ME-001** — model validators | `ads/models.py:533-588` | `RegexValidator(KEY_FORMAT_REGEX)` on `image`, `thumbnail_small`, `thumbnail_medium`, `thumbnail_large` |
| **ME-001** — DB CheckConstraints | `ads/models.py:600-619` | 4 `CheckConstraint`s in `AdImage.Meta.constraints` using `Q(field__regex=KEY_FORMAT_REGEX)` |
| **ME-001** — save() guard | `ads/models.py:635` | `assert_storage_key_contained(self.image)` before SHA-256 computation |
| **ME-001** — serving path | `ads/views/listings.py:114,167` | `_serve_image` and `media_gate` both call `assert_storage_key_contained` |
| **ME-001** — regression tests | `test_media_security.py` | `TestPhysicalDeletion.test_delete_photo_rejects_traversal_key` (l.349); `TestPathTraversalRejection` (l.377) |
| **NEW-ME-007** — enum IDs | `core/enums.py:38-39` | `SWEEP_ORPHANED_MEDIA = 103`; `CATALOG_LOAD = 104` |
| **NEW-ME-007** — scheduler | `entrypoint-scheduler.sh:33` | `sweep_orphaned_media` in `hourly_commands` |
| **NEW-ME-007** — lock tests | `test_sweep_lock_structure.py:43,67` | Command in `SWEEP_COMMANDS` + `_LOCK_TARGET_MODULES` |
| **NEW-ME-007** — CI assertion | `test_advisory_lock_ids.py:63-93` | `TestAdvisoryLockIdReferences` AST-scans all `AdvisoryLockId.*` refs |
| **NEW-ME-007** — routes through delete_photo | `sweep_orphaned_media.py:110` | `delete_photo(key)` not raw `os.remove` |
| **ME-003-secondary** | `filesystem.py:173-190` | `_record_deletion_error()` persists to `MediaDeletionError` model (`apps/media/models.py`) |
| **ME-002 (2/7)** — storage_keys() | `ads/models.py:672` | `AdImage.storage_keys()` returns image + truthy thumbnail keys |
| **ME-002 (2/7)** — consent_hard_delete | `consent_hard_delete.py:74` | Uses `img.storage_keys()` list comprehension |
| **ME-002 (2/7)** — deletion.py | `deletion.py:207` | Uses `img.storage_keys()` list comprehension |
| **ME-002** — regression test | `test_sweep_commands.py:318-356` | `test_collects_thumbnail_keys_for_media_cleanup` for consent_hard_delete |
| **ME-002** — storage_keys unit tests | `test_adimage_storage_keys.py` | 5 unit tests covering all key combinations |

### OPEN (requires implementation)

| Finding | What's needed | Key locations |
|---|---|---|
| **ME-002 (5 remaining sweeps)** | Replace `values_list("image", flat=True)` with `img.storage_keys()` | delete_sweep.py:65-69, purge_deleted_ads.py:66-70, purge_rejected_ads.py:65-69, purge_failed_ads.py:64-68, sweep_drafts.py:63-67 |
| **ME-004 (HIGH)** | `len(photos) >= 5` rejection before `download_photo`; fix inverted "at least 1" → "at most 5" message | `ad_create.py:646-720` (process_photos) |
| **ME-006 (HIGH)** | Wire `check_upload_rate_limit(user_id)` before `download_photo` | `ad_create.py:646-720`; `rate_limit.py:30` has 0 call sites |
| **ME-005 (MEDIUM)** | Set `Image.MAX_IMAGE_PIXELS` project-wide | 0 matches in src/ |

## Key architecture notes

- Bot imports `delete_photo`, `validate_photo`, etc. from `apps.media.services.filesystem` (not `telegram_bot.services.media` — the old module no longer exists).
- `check_upload_rate_limit` (rate_limit.py:30) uses atomic `cache.add`/`cache.incr` pattern (10 req/60s, keyed by `bot_upload_rl:{user_id}`). Zero call sites — dead code.
- `check_contact_start_rate_limit` IS wired (contact.py:20) — the upload limiter should follow the same pattern.
- In `process_photos`, `user_id` is available via `data = await state.get_data()` → `data["user_id"]` (set by `cmd_post` at FSM initiation).
- `PhotoCountPayload.photo_count: Annotated[int, Field(ge=1, le=5)]` at `message_payloads.py:56-58` — the 5-photo cap constant.
- `AdImage.storage_keys()` pattern in consent_hard_delete.py (lines 71-75):
  ```python
  storage_keys = [
      key
      for img in AdImage.objects.filter(ad__user_id__in=user_ids)
      for key in img.storage_keys()
  ]
  ```
- `MediaConfig` at `apps/media/apps.py` has no `ready()` override — natural place for `MAX_IMAGE_PIXELS`.
- Test DB is PostgreSQL in Docker (`mko-bazuna-test`, port 5433); tests must run via Docker Compose.

## Ordering constraints
- ME-002 (5 sweeps) depends on ME-001 containment (already done ✅)
- ME-004 + ME-006 both modify `process_photos` → same PR
- ME-005 is fully independent
