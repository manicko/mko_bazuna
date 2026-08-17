# Media Fix Matrix — Validated Audit Findings (MED-001..MED-008)
# Status: Classification + remediation research complete → IMPLEMENTING.
# Source of truth: `.ai/audit/99-validation/07-media-validated-findings.md`

## Legend
- Severity: C=critical, H=high, M=medium, L=low
- Path convention: `apps.xxx` (pythonpath includes `src/backend`, app `name = "apps.xxx"`)

## Verified facts (from source, not assumptions)
- `AdImage` (ads/models.py:436-550): fields `image CharField(64) db_index`, `thumbnail_small/medium/large CharField(64)`, `sha256 CharField(64, db_index=True, default="")`. sha256 already has db_index — NO migration needed for MED-002/008.
- `AdImage.save()` (models.py:495-527): currently auto-hashes from DISK file + dedups by `ad__user_id`. MED-008 changes the gate condition.
- `save_photo` (ad_create.py:586-614): async, writes CLEANED bytes (`strip_photo_exif`) via `os.open(O_CREAT|O_EXCL)`. Returns `storage_key: str`. AdImage rows created LATER in `update_ad_and_moderate` (ad_create.py:766-775) where user_id context exists.
- `process_photos` (ad_create.py:358-412): `data["user_id"]` available (set in cmd_post via create_draft_ad). Current guard only on 'done': `PhotoCountPayload(photo_count=count)` (ge=1, le=5); bare `except Exception` at ad_create.py:367.
- `delete_photo(key)` (media.py:85-123): deletes ONLY the main file — never thumbnails. Root cause of MED-001.
- Thumbnails: explicit fields, naming `{stem}-{size.value}.jpg` (thumbnails.py:75). No webp variant. Per-row unique EXCEPT main `image` can be shared via MED-002 dedup-reuse.
- `pre_delete` signal REJECTED (see MED-001). `CACHES` = LocMemCache (`config/settings/base.py:221`); `MEDIA_ROOT` is a Path.
- Tests spy on `delete_photo` in COMMAND module namespace:
  - `test_sweep_commands.py:739` `delete_sweep.delete_photo` (raise, assert TX-then-fs)
  - `test_sweep_commands.py:619` `purge_deleted_ads.delete_photo` (record key)
  - `test_deletion.py:273` `deletion.delete_photo` (withdraw returns keys)
  - `test_deletion.py:333` asserts `soft_delete_user_ads` is DB-only (no delete_photo)

---

## MED-001 — CRITICAL / Complex / Orphaned thumbnails on deletion
### Decision: explicit-only `delete_adimage_files()` helper (NO pre_delete signal)
Signal rejected because: it fires DURING `queryset.delete()` cascade INSIDE the tx, deleting files before commit → violates the TX-then-FS property the spy tests enforce (`test_file_deletion_after_commit_not_inside_transaction`). It would also double-delete against explicit calls. Explicit post-tx calls cover every known deletion path (bot-driven; no Django admin).

### Edits
1. **`telegram_bot/services/media.py`** — add:
   ```python
   def delete_adimage_files(ad_image) -> None:
       """Delete an AdImage's thumbnail siblings (always) + main image (only if orphan).
       Thumbnails are per-row unique -> always delete. The main ``image`` key may be
       shared across AdImage rows (MED-002 dedup-reuse) -> deleted only when no other
       row references it (orphan check). Safe to call after ORM rows are gone (sweep
       path): orphan check returns True for all -> delete all (2nd call on shared key
       is a silent FileNotFoundError)."""
       for field in ("thumbnail_small", "thumbnail_medium", "thumbnail_large"):
           key = getattr(ad_image, field, None)
           if key:
               delete_photo(key)
       main = getattr(ad_image, "image", None)
       if main and _image_key_is_orphan(main, exclude=ad_image):
           delete_photo(main)
   ```
   - `_image_key_is_orphan(image_key, exclude=None) -> bool`: `AdImage.objects.filter(image=image_key)`; if `exclude` given and it's an instance with pk, `.exclude(pk=exclude.pk)`; returns `not qs.exists()`. (Lazy `from apps.ads.models import AdImage` inside helper to avoid any import cycle concern at module load — though models.py doesn't import media.py, lazy import is safe & consistent with codebase style.)
   - Type hint `ad_image` via `TYPE_CHECKING` + `from apps.ads.models import AdImage` under the guard (no runtime import needed).

2. **5 sweep commands** (`delete_sweep`, `purge_deleted_ads`, `purge_rejected_ads`, `purge_failed_ads`, `sweep_drafts`) + `consent_hard_delete`:
   - Change import: `delete_photo` → `delete_adimage_files`.
   - Inside tx: replace `storage_keys = list(AdImage...values_list("image"))` with `images = list(AdImage.objects.filter(ad_id__in=ad_ids))` (keep `only()`? No — need thumbnail fields; `all()` default is fine, but add `.only("image","thumbnail_small","thumbnail_medium","thumbnail_large")`? Simpler: plain `list(...)`).
   - After tx: `for img in images: delete_adimage_files(img)`. Update logger counts to `len(images)`.

3. **`soft_delete_user_ads` (deletion.py:197-205)**: before `AdImage.objects.filter(...).delete()`, collect ALL keys (image + non-empty thumbnails) into `draft_storage_keys` (flat list[str]). withdraw_consent's existing `delete_photo` loop (line 158-159) unchanged → deletes all. `AdImage.objects.filter(...).delete()` then removes rows.
   - Test-safe: `test_soft_delete_user_ads_returns_keys_not_called` creates one AdImage with `image="orphan-key.jpg"` only → returns `["orphan-key.jpg"]` → `"orphan-key.jpg" in result` ✓, `isinstance(k,str)` ✓, `called == []` ✓.
   - `test_withdraw_returns_storage_keys`: one AdImage `image="test-draft-key.jpg"` → returns same → `deleted_keys == result` ✓.

4. **`delete_draft` (ad_create.py:529-531)**: `for img in ad.images.all(): delete_photo(img.image)` → `delete_adimage_files(img)`. (Called before `ad.delete()` cascade; rows still exist → orphan check meaningful. Tests DB-only, no spy — safe.)

5. **`delete_photo` itself (media.py)**: UNCHANGED — keeps its retry/backoff semantics; still unit-tested by `test_media.py` + `test_media_security.py::TestPhysicalDeletion`.

### Test updates (2 files)
- `test_sweep_commands.py:739` → monkeypatch `delete_sweep.delete_adimage_files` (was `delete_photo`). Spy `_raise` replaces the function; `delete_adimage_files(img)` → raises after tx. ✓ ad gone.
- `test_sweep_commands.py:619` → monkeypatch `purge_deleted_ads.delete_adimage_files`; spy records `ad_image.image`.
- `test_deletion.py`: NO changes (soft_delete returns flat keys, withdraw uses delete_photo — tests already pass).

---

## MED-002 — MEDIUM / Complex / Duplicate file writes across user's ads
### Decision: hash-before-write in `save_photo` (not model)
`save_photo` is where files are written incrementally in `process_photos`. Move pre-compute + dedup there (before write) per research Alternative A-modified.

### Edits
1. **`media/services/hash_service.py`**: add `calculate_sha256_from_bytes(data: bytes) -> str` (hashlib, no file IO). No migration.

2. **`ad_create.py save_photo` (586-614)**: signature `save_photo(storage_key, photo_bytes, user_id=None) -> tuple[str, str]`:
   - `cleaned = strip_photo_exif(photo_bytes)` once; refactor inner `_write` to take pre-cleaned bytes (remove its internal `strip_photo_exif` — single responsibility).
   - `sha256 = FileHashService.calculate_sha256_from_bytes(cleaned)`.
   - If `user_id is not None`: `existing = await _find_duplicate(user_id, sha256)` (sync_to_async) → if found: `logger.info(...)`; return `(existing.image, sha256)` — NO write.
   - Else: write cleaned via to_thread; return `(key, sha256)`.
   - Add `_find_duplicate(user_id, sha256) -> AdImage | None` helper wrapped in sync_to_async (lazy import).

3. **`ad_create.py process_photos` (402)**: `storage_key, photo_sha = await save_photo(generate_storage_key(), photo_bytes, user_id=data.get("user_id"))`; append `"sha256": photo_sha` to photos dict.

4. **`ad_create.py update_ad_and_moderate` (767)**: `AdImage.objects.create(..., sha256=photo.get("sha256", ""))`.

5. **Model `save()` (008) defense-in-depth**: condition `or not self.sha256` → `and not self.sha256` so bot-predicted hashes aren't recomputed from disk. Model dedup block retained for non-bot paths.

### Rejection rationale
- UniqueConstraint on (sha256, user): seed bulk_create shares images across same-user ads; backfill violates. Rejected (audit also exempts seed, but it's a footgun). `db_index` already present.

---

## MED-008 — ADVISORY / Low / Model save() recompute
### Edit
- `ads/models.py:503`: `if self._state.adding or not self.sha256:` → `if self._state.adding and not self.sha256:`

---

## MED-003 — HIGH / Low / Bot photo limits + error hygiene
### Edits
1. **`process_photos` photo branch (after validate, before save_photo)**: `if len(photos) >= 5: await message.answer("Maximum 5 photos per ad..."); return`.
2. **`process_photos` 'done' branch (367-370)**: `except Exception:` → `from pydantic import ValidationError` + `except ValidationError:`; message → `f"Please send 1-5 photos (you have {count})."`.
3. **New `telegram_bot/services/rate_limit.py`**: `PhotoUploadRateLimiter.check(user_id: int, limit=10, period=60) -> bool` mirroring `search/services/rate_limit.py` (cache.add/incr). Called in save_photo (pre-write) via sync_to_async. (Bot single-process; LocMemCache ok.)

---

## MED-005 — MEDIUM / Low / Orphan sweep backstop
### Edit
- New `apps/media/management/commands/sweep_orphaned_media.py`: walk MEDIA_ROOT, exclude `seed/`, diff vs live `AdImage.image`/`thumbnail_*` keys, delete orphans. Idempotent cron.

---

## MED-006 — LOW / Low / EXIF strip test (integration)
### Edit
- New `tests/test_media_exif_strip.py`: EXIF JPEG → `save_photo` (via tmp MEDIA_ROOT) → assert no `Exif\x00\x00` on disk. Reuse `jpeg_with_exif` fixture style from `ads/tests/test_media_security.py`.

---

## MED-007 — LOW / Low / Security headers on dev image serve
### Edit
- `ads/views/listings.py:90-102` `_serve_image`: on `HttpResponse`, set `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Content-Security-Policy: default-src 'none'; img-src 'self'`, `Content-Disposition: inline`. (DEBUG only.)

---

## Implementation Order (dependency-sorted)
| Step | Finding | Notes |
|------|---------|-------|
| 1 | MED-008 | 1-line model condition change (unblocks MED-002 model side) |
| 2 | MED-001 | helper + 7 call sites + 2 test spy updates |
| 3 | MED-002 | hash_service + save_photo refactor |
| 4 | MED-003 | count guard + ValidationError + rate limiter |
| 5 | MED-007 | headers |
| 6 | MED-006 | test |
| 7 | MED-005 | orphan sweep |

## Verification
- `uv run ruff check <paths>`; `uv run basedpyright <paths>` (local).
- `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm test` (PG test DB required).
- Tests updated to spy `delete_adimage_files` (2) — intent preserved.

## Files Touched
```
src/backend/apps/media/services/hash_service.py           # MED-002
src/backend/apps/ads/models.py                            # MED-001(helper? no),MED-008
src/telegram_bot/services/media.py                        # MED-001 helper delete_adimage_files
src/telegram_bot/services/rate_limit.py                   # NEW MED-003
src/telegram_bot/handlers/ad_create.py                    # MED-002/003/001(delete_draft)
src/backend/apps/media/management/commands/sweep_orphaned_media.py # NEW MED-005
src/backend/apps/ads/views/listings.py                    # MED-007
src/backend/apps/users/services/deletion.py               # MED-001 (soft_delete collect thumbs)
src/backend/apps/core/management/commands/{delete_sweep,purge_rejected_ads,purge_failed_ads,sweep_drafts,purge_deleted_ads,consent_hard_delete}.py # MED-001
src/backend/apps/core/tests/test_sweep_commands.py        # MED-001 spy update (2 tests)
tests/test_media_exif_strip.py                            # NEW MED-006
```
NO migrations required (sha256 indexed field already exists; all changes are code/behavior).
