# Media Subsystem Audit — Findings Report

**Phase:** 07 — Media subsystem audit  
**Date:** 2026-09-12  
**Auditor:** Kilo (poolside/laguna-s-2.1:free)  
**Scope:** Image upload, storage, serving, thumbnail lifecycle, orphan cleanup, retention sweeps  
**Status:** Complete  

---

## Executive Summary

The media subsystem has a solid architectural foundation with well-structured services (`AdImageService`, `ThumbnailService`, `Filesystem`), proper path-traversal defenses in `media_gate`, and TX-then-Filesystem ordering in sweep commands. However, several critical data-integrity and data-loss risks were identified:

- **1 CRITICAL** — Cancel-after-submit destroys original image files for published ads
- **2 HIGH** — No physical file cleanup on `AdImage` cascade-delete; orphan sweep deletes in-flight uploads
- **4 MEDIUM** — `delete_draft` skips thumbnail cleanup; unbounded Telegram download; no DB indexes on lookup fields; DRAFT retention policy mismatch (30 min vs 7 days)
- **3 LOW** — Incomplete EXIF strip; `_serve_image` docstring/code mismatch; dead code in `_walk_media_files`; missing cache headers

---

## Findings

### CRITICAL — Cancel after successful submit destroys ad images

**File:** `src/telegram_bot/handlers/ad_create.py:838-853`  
**Spec reference:** `docs/04-user-stories/seller-stories.md:39` (idle timeout)

**What happens:**

1. User uploads photos → storage keys saved to FSM state `photos` list
2. User types `"confirm"` in `process_preview` → `submit_ad()` succeeds, generates thumbnails, creates `AdImage` rows, transitions ad from DRAFT → ON_MODERATION
3. `state.clear()` is **NOT called** on the success path (line 848 only clears on failure)
4. FSM state retains `ad_id` and `photos` (original image storage keys)
5. User types `"cancel"` → `cmd_cancel()` (line 106) runs:
   - Deletes original photo files from disk via `delete_photo(photo["storage_key"])` (lines 114-117)
   - Calls `delete_draft(data["ad_id"])` (line 119) → returns early because ad is no longer DRAFT (line 884)
   - Calls `state.clear()` (line 121)
6. **Result:** The successfully submitted ad has original image files **destroyed on disk**. `AdImage` rows remain in DB pointing to deleted files. Thumbnails are also orphaned (see MED-001).

**Evidence:**

```python
# ad_create.py:838-853
if is_valid:
    await message.answer("Ad submitted for moderation!")
    # ↑ state.clear() NOT called here — FSM state persists with ad_id + photos
else:
    await message.answer("Ad failed moderation...")
    await state.clear()    # ← only reached on failure
    return
```

```python
# ad_create.py:106-124
async def cmd_cancel(message, state):
    data = await state.get_data()
    if "ad_id" in data:
        photos = data.get("photos", [])
        for photo in photos:
            await asyncio.to_thread(delete_photo, photo["storage_key"])  # deletes originals
        await delete_draft(data["ad_id"])  # returns early (ad not DRAFT)
    await state.clear()
```

**Impact:** A buyer could encounter broken image links on a published ad if the seller mistakenly types "cancel" after confirming. Data loss of submitted ad media.

**Severity:** CRITICAL (data loss)

**Recommendation:** Call `state.clear()` after successful `submit_ad` (line 842). Also guard `cmd_cancel` against deleting photos for non-DRAFT ads.  
**Effort:** Small  
**Priority:** Mandatory

---

### HIGH — No physical file cleanup on AdImage cascade-delete

**File:** `src/backend/apps/ads/models.py:521-670`  
**Spec reference:** `docs/02-database/db-retention.md:102` (describes explicit `delete_photo()` loop for consent hard-delete)

**What happens:**

The `AdImage` model has `ad = ForeignKey(..., on_delete=models.CASCADE)` (line 529). When an `Ad` is hard-deleted, Django ORM cascades and deletes `AdImage` rows at the DB level, but **no `delete()` override or `post_delete` signal** exists on `AdImage` to delete the physical files (original + thumbnails). The `AdImage` model defines `save()` (line 625) and `storage_keys()` (line 672) but **no `delete()`**.

The only paths that correctly clean up physical files are:
- `sweep_drafts` command (line 66: uses `img.storage_keys()`)
- `soft_delete_user_ads` (line 201: uses `img.storage_keys()`)
- `consent_hard_delete` (described in `db-retention.md:102`)
- `sweep_orphaned_media` (backstop, deletes unreferenced files)

But normal ad deletion via the web UI or moderation rejection flows that hard-delete ads will orphan physical files until the next hourly orphan sweep.

**Evidence:**

```python
# models.py:521-676 — AdImage has no delete() override, no signals
class AdImage(models.Model):
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, ...)
    image = models.CharField(...)
    thumbnail_small = models.CharField(...)
    # ...
    def save(self, *args, **kwargs) -> None: ...   # SHA-256 auto-compute
    def storage_keys(self) -> list[str]: ...        # returns all keys
    # ↑ NO delete() method, NO post_delete signal receiver
```

```python
# models.py:527-532
ad = models.ForeignKey(
    Ad,
    on_delete=models.CASCADE,   # ORM cascade deletes DB rows only
    related_name="images",
)
```

**Impact:** Physical files accumulate on disk between sweep runs. Disk usage grows unbounded for high-volume deployments. The hourly `sweep_orphaned_media` mitigates this but creates a window for race conditions (see MED-002).

**Severity:** HIGH (operational reliability, disk exhaustion risk)

**Recommendation:** Add a `post_delete` signal on `AdImage` that calls `delete_photo()` for all keys returned by `storage_keys()`, or override `AdImage.delete()` to clean up files.  
**Effort:** Small  
**Priority:** Recommended

---

### HIGH — Orphan sweep deletes in-flight uploads

**File:** `src/backend/apps/media/management/commands/sweep_orphaned_media.py`  
**Spec reference:** `docs/02-database/db-retention.md:124` (hourly scheduler)

**What happens:**

The `sweep_orphaned_media` command (line 34-43) collects all storage keys referenced by `AdImage` rows, then walks `MEDIA_ROOT` and deletes any file not in that set. However, during the bot upload flow, photos are saved to disk via `save_photo()` (line 699 in `ad_create.py`) and stored in FSM state **before** `AdImage` rows are created during `submit_ad()` (line 168). If the sweep runs while a seller is mid-upload, their just-saved photos are classified as orphans and deleted.

The scheduler runs hourly (`docs/02-database/db-retention.md:124`), and the upload flow involves:
1. `download_photo()` — downloads from Telegram
2. `save_photo()` — writes to disk + EXIF strip
3. `photos.append({"storage_key": ...})` — stored in FSM state
4. ... (user continues uploading)
5. `submit_ad()` → `AdImageService.create_or_skip()` — creates DB rows

Steps 2-5 can span minutes. Any photo saved at step 2 but not yet committed at step 5 is vulnerable to deletion by the sweep.

**Evidence:**

```python
# ad_create.py:681-711 — save to disk and FSM state, NOT yet AdImage row
photo_bytes = await download_photo(photo.file_id, message.bot)        # step 2
storage_key = await save_photo(generate_storage_key(), photo_bytes)   # step 3: file on disk
photos.append({"storage_key": storage_key, ...})                        # step 4: FSM state only
await state.update_data(photos=photos)
```

```python
# submission.py:167-176 — AdImage row created only here (after thumbnails)
with transaction.atomic():
    for photo in input.photos:
        AdImageService.create_or_skip(ad=ad, image=photo["storage_key"], ...)
```

Meanwhile, `sweep_orphaned_media` at line 89-90:
```python
referenced = _collect_referenced_keys()  # from AdImage rows only
on_disk = set(_walk_media_files(media_root))  # includes in-flight uploads
orphans = on_disk - referenced  # in-flight uploads classified as orphans
```

**Impact:** In-flight photo uploads can be silently deleted by the hourly sweep, causing the seller to see "Photo saved" messages followed by missing images when they try to upload more photos or submit.

**Severity:** HIGH (data loss, user-facing)

**Recommendation:** Exclude in-flight FSM upload keys from orphan sweep, or add a "pending" table/model to track uploaded files. Alternatively, accept uploads into a staging directory excluded from the sweep, moving files to permanent storage on successful submit.  
**Effort:** Medium  
**Priority:** Recommended

---

### MEDIUM — `delete_draft` does not delete thumbnail files

**File:** `src/telegram_bot/handlers/ad_create.py:875-896`  
**Spec reference:** `db-retention.md:102` (describes `storage_keys()` usage for cleanup)

**What happens:**

The `delete_draft` function iterates `ad.images.all()` and calls `delete_photo(img.image)` for each (line 892), but does **not** delete thumbnail variants (`thumbnail_small`, `thumbnail_medium`, `thumbnail_large`). The `AdImage` model's `storage_keys()` method (line 672) returns all keys including thumbnails, but it is not used here.

This is an inconsistency: `sweep_drafts.py` (line 66), `soft_delete_user_ads` (line 201), and `consent_hard_delete` all correctly use `img.storage_keys()` for cleanup. `delete_draft` is the only deletion path that does not.

**Evidence:**

```python
# ad_create.py:875-896
async def delete_draft(ad_id: int) -> None:
    @sync_to_async
    def _delete() -> None:
        try:
            ad = Ad.objects.get(id=ad_id, status=AdStatus.DRAFT)
        except Ad.DoesNotExist:
            return
        for img in ad.images.all():
            delete_photo(img.image)  # ← only original, NOT storage_keys()
        ad.delete()
    await _delete()
```

Compare with the correct pattern in `sweep_drafts.py:63-66`:
```python
storage_keys = [
    key
    for img in AdImage.objects.filter(ad_id__in=ad_ids)
    for key in img.storage_keys()  # ← all keys: image + thumbnails
]
```

**Impact:** Thumbnail files accumulate as orphans when drafts are cancelled via the bot. The hourly `sweep_orphaned_media` eventually reclaims them, but until then disk usage grows.

**Severity:** MEDIUM (waste, eventual consistency via backstop)

**Recommendation:** Replace `delete_photo(img.image)` with iteration over `img.storage_keys()`.  
**Effort:** Trivial  
**Priority:** Recommended

---

### MEDIUM — Telegram photo downloaded before size validation

**File:** `src/telegram_bot/handlers/ad_create.py:681-690`

**What happens:**

The upload handler (line 675-714) checks the per-user rate limit (line 675), then immediately downloads the full photo bytes from Telegram (line 681: `download_photo(photo.file_id, ...)`) **before** calling `validate_photo` (line 690). The `validate_photo` function checks the ~2MB size limit (line 99 in `filesystem.py`).

This means a malicious or buggy client can send arbitrarily large files that are fully downloaded into bot memory before being rejected. The rate-limit check at line 675 is per-user per-window, not a file-size guard.

**Evidence:**

```python
# ad_create.py:681-695
photo_bytes = await download_photo(photo.file_id, message.bot)  # full download
if not photo_bytes:
    await message.answer("Failed to download photo.")
    return
is_valid, error = validate_photo(photo_bytes)  # size check happens here
if not is_valid:
    await message.answer(f"Invalid: {error}")
    return
```

Telegram's Bot API does not support range requests or size pre-checks on `file_id` downloads; the entire file is fetched. However, Telegram does report `file_size` in the `PhotoSize` object, which could be checked before download.

**Impact:** Memory exhaustion vector for the bot process. A user could upload a 50MB file, consuming bot memory and bandwidth, before the size check rejects it.

**Severity:** MEDIUM (DoS / resource exhaustion)

**Recommendation:** Check `photo.file_size` (Telegram provides this) before calling `download_photo()`. If `file_size` exceeds the max, reject immediately. Additionally, use streaming download with a byte cap.  
**Effort:** Small  
**Priority:** Recommended

---

### MEDIUM — No DB indexes on AdImage lookup fields

**File:** `src/backend/apps/ads/models.py:597-620`  
**Spec reference:** `docs/02-database/db-indexes.md:248-251`

**What happens:**

The `AdImage.Meta` class defines only `constraints` (check constraints on key format) and `db_index=True` on `sha256` (line 591). There are **no `indexes`** entries. The `media_gate` view queries by `image` and `thumbnail_small/medium/large` fields on every image request:

```python
# listings.py:169-177
key_q = (
    Q(image=image_key)
    | Q(thumbnail_small=image_key)
    | Q(thumbnail_medium=image_key)
    | Q(thumbnail_large=image_key)
)
if not AdImage.objects.filter(key_q).exists():
    raise Http404("Image not found")
# ... second query for published check
```

Without indexes on these fields, every image request triggers sequential scans on the `ad_images` table. The spec doc `db-indexes.md:248` only documents `IX_adimages_sha256` for deduplication and explicitly notes "no index" for the DRAFT sweep.

**Impact:** Image request latency scales poorly with ad_images table size. On a production listing page with 24 ads × 3 images, each image request does 2 unindexed queries.

**Severity:** MEDIUM (performance, scalability)

**Recommendation:** Add database indexes on `image`, `thumbnail_small`, `thumbnail_medium`, and `thumbnail_large` fields. Consider a composite approach or partial indexes if certain lookups are more common.  
**Effort:** Small (add `models.Index(...)` entries to `Meta.indexes`, generate migration)  
**Priority:** Recommended

---

### MEDIUM — DRAFT retention policy mismatch (30 min vs 7 days)

**Code:** `src/backend/apps/core/management/commands/sweep_drafts.py:45`  
**Spec (authoritative):** `docs/02-database/db-retention.md:32,82` — DRAFT retention = 7 days  
**Spec (suggestion):** `docs/01-spec/technical-specification.md:152` — "idle timeout (e.g. 30 min)"

**What happens:**

The `sweep_drafts` command uses `timedelta(minutes=30)` (line 45) to determine which DRAFT ads to delete. However, the authoritative retention policy in `db-retention.md` specifies **7 days** for DRAFT ads. The `technical-specification.md` uses "(e.g. 30 min)" as an example, which may have been interpreted as the implementation value, but `db-retention.md` is documented as the "single source of truth" (line 21).

The test suite at `test_sweep_commands.py:189` also documents "30-minute window" in its docstring, reinforcing the implementation but contradicting the policy doc.

**Impact:** DRAFT ads are purged 30 minutes after creation if the seller doesn't complete the flow. This is far more aggressive than the documented 7-day retention, potentially causing user frustration if they are interrupted mid-flow and cannot resume.

**Severity:** MEDIUM (policy deviation, user experience)

**Recommendation:** Align the implementation with the stated policy (7 days), or update `db-retention.md` to specify 30 minutes if that is the intended UX. The current inconsistency between docs is itself the issue.  
**Effort:** Trivial (change `timedelta` or update docs)  
**Priority:** Recommended

---

### LOW — Incomplete EXIF/metadata stripping in `strip_photo_exif`

**File:** `src/backend/apps/media/services/filesystem.py:193-211`

**What happens:**

The `strip_photo_exif` function (line 193) removes EXIF data by calling `img.info.pop("exif", None)` (line 208), but does **not** remove `icc_profile` from `img.info`. When Pillow re-encodes the JPEG (line 210: `img.save(buf, format="JPEG", optimize=True)`), any remaining `icc_profile` in `img.info` is written to the output file.

ICC profiles can contain:
- Camera manufacturer/model information
- Color calibration data
- Embedded serial numbers (in some profiles)

Additionally, `ImageOps.exif_transpose(img)` (line 207) creates a new image that copies the original's `info` dict, preserving the `icc_profile`.

**Evidence:**

```python
# filesystem.py:193-211
def strip_photo_exif(photo_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(photo_bytes))
    img = ImageOps.exif_transpose(img)   # copies info dict, including icc_profile
    img.info.pop("exif", None)          # ← only EXIF removed, icc_profile remains
    buf = io.BytesIO()
    img.save(buf, format="JPEG", optimize=True)  # ← writes icc_profile if present
    return buf.getvalue()
```

**Impact:** Low privacy/security risk (icc_profile metadata persists). File size may also be slightly larger than necessary. The function's docstring claims it "hardens against malicious JPEGs" but the stripping is incomplete.

**Severity:** LOW (privacy/metadata leak)

**Recommendation:** Also pop `icc_profile` from `img.info` before saving: `img.info.pop("icc_profile", None)`. Optionally use `piexif` or Pillow's `exif=b""` parameter for thorough stripping.  
**Effort:** Trivial  
**Priority:** Recommended

---

### LOW — `_serve_image` docstring claims FileResponse but uses HttpResponse

**File:** `src/backend/apps/ads/views/listings.py:100-117`

**What happens:**

The `_serve_image` function docstring (line 102) states: "Uses `FileResponse` to stream the file from `MEDIA_ROOT`." However, the actual implementation reads the entire file into memory (`data = f.read()`, line 116) and wraps it in `HttpResponse(data, content_type="image/jpeg")` (line 117). This defeats the purpose of streaming and can cause memory pressure when serving large images in development.

**Evidence:**

```python
# listings.py:100-117
def _serve_image(image_key: str) -> HttpResponse:
    """...Uses ``FileResponse`` to stream the file from ``MEDIA_ROOT``..."""
    # ...
    with open(file_path, "rb") as f:
        data = f.read()           # ← entire file in memory
    return HttpResponse(data, content_type="image/jpeg")  # ← not FileResponse
```

**Impact:** Memory inefficiency in development. Doc/code mismatch creates maintenance confusion.

**Severity:** LOW (performance, doc accuracy)

**Recommendation:** Replace with `FileResponse(open(file_path, "rb"), content_type="image/jpeg")` to stream, matching the docstring. Or update the docstring if the current behavior is intentional.  
**Effort:** Trivial  
**Priority:** Recommended

---

### LOW — Dead code in `_walk_media_files`

**File:** `src/backend/apps/media/management/commands/sweep_orphaned_media.py:46-60`

**What happens:**

Lines 51-53 contain a dead code block:

```python
if rel_dir == ".":
    if _SEED_SUBDIR in os.listdir(media_root):
        pass  # not in the top-level dir, handled below
```

The `if rel_dir == "."` block with `pass` does nothing. The seed directory exclusion is actually handled by the check at line 55: `if rel_dir == _SEED_SUBDIR or rel_dir.startswith(f"{_SEED_SUBDIR}/"): continue`. The dead block is confusing for maintainers and suggests incomplete refactoring.

**Evidence:**

```python
# sweep_orphaned_media.py:46-60
def _walk_media_files(media_root: str) -> list[str]:
    files: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(media_root):
        rel_dir = os.path.relpath(dirpath, media_root)
        if rel_dir == ".":                      # ← dead block
            if _SEED_SUBDIR in os.listdir(media_root):
                pass  # not in the top-level dir, handled below  ← does nothing
        if rel_dir == _SEED_SUBDIR or rel_dir.startswith(f"{_SEED_SUBDIR}/"):
            continue                            # ← actual seed exclusion
        for name in filenames:
            rel_path = os.path.join(rel_dir, name) if rel_dir != "." else name
            files.append(rel_path)
    return files
```

**Impact:** Code clarity and maintainability. No functional impact.

**Severity:** LOW (code quality)

**Recommendation:** Remove the dead `if rel_dir == "."` block (lines 51-53).  
**Effort:** Trivial  
**Priority:** Recommended

---

### LOW — No cache-control headers on `media_gate` responses

**File:** `src/backend/apps/ads/views/listings.py:120-198`  
**Spec reference:** `docs/02-database/db-retention.md:102` (describes immutable storage keys)

**What happens:**

The `media_gate` view does not set any cache headers on its responses (no `Cache-Control`, `ETag`, or `Last-Modified`). All other public views use the `never_cache` decorator (confirmed in `logout.py:16`, `consent.py:277,360`, `preferred_city.py:26`). The `media_gate` view neither uses `never_cache` nor sets explicit caching directives.

Since image storage keys are UUID v4-based and immutable (confirmed in `AdImage` model: "UUID v4 + .jpg, no ad_id/user/telegram PII"), images are excellent candidates for long-term browser/CDN caching. However, without explicit headers, browser caching behavior is undefined — some proxies may cache, some may not revalidate properly.

**Impact:** Inconsistent caching behavior. Missed opportunity for performance optimization via browser caching of immutable assets.

**Severity:** LOW (performance, operational hygiene)

**Recommendation:** Add `Cache-Control: public, max-age=31536000, immutable` for production (X-Accel-Redirect) responses, since UUID keys are immutable. For development fallback (`_serve_image`), add appropriate no-cache headers if desired.  
**Effort:** Small  
**Priority:** Recommended

---

## Summary Table

| ID | Title | Severity | Effort | File | Lines |
|----|-------|----------|--------|------|-------|
| CR-001 | Cancel after submit destroys ad images | CRITICAL | Small | `ad_create.py` | 838-853 |
| HIGH-001 | No file cleanup on AdImage cascade-delete | HIGH | Small | `models.py` | 521-670 |
| HIGH-002 | Orphan sweep deletes in-flight uploads | HIGH | Medium | `sweep_orphaned_media.py` | 34-43, 89-92 |
| MED-001 | `delete_draft` doesn't delete thumbnails | MEDIUM | Trivial | `ad_create.py` | 875-896 |
| MED-002 | Telegram download before size validation | MEDIUM | Small | `ad_create.py` | 681-690 |
| MED-003 | No DB indexes on AdImage lookup fields | MEDIUM | Small | `models.py` | 597-620 |
| MED-004 | DRAFT retention mismatch (30 min vs 7 days) | MEDIUM | Trivial | `sweep_drafts.py` | 45 |
| LOW-001 | Incomplete EXIF strip (icc_profile) | LOW | Trivial | `filesystem.py` | 193-211 |
| LOW-002 | `_serve_image` docstring/code mismatch | LOW | Trivial | `listings.py` | 100-117 |
| LOW-003 | Dead code in `_walk_media_files` | LOW | Trivial | `sweep_orphaned_media.py` | 51-53 |
| LOW-004 | No cache-control on media responses | LOW | Small | `listings.py` | 120-198 |

---

## Observations

### Positive patterns already in place

- **TX-then-Filesystem**: `sweep_drafts.py:70-76` deletes DB rows inside `transaction.atomic()`, then deletes physical files after commit — correct ordering to avoid orphan-on-rollback
- **`storage_keys()` method**: `AdImage.storage_keys()` (line 672) returns all keys (image + thumbnails) — used correctly by `sweep_drafts`, `soft_delete_user_ads`, and `consent_hard_delete`
- **Path traversal defense**: `assert_storage_key_contained()` validates keys are within MEDIA_ROOT — `media_gate` test suite (`test_media_security.py:376-435`) verifies `../`, encoded traversal, NUL bytes, and absolute paths
- **Seed exclusion**: `sweep_orphaned_media` correctly excludes `seed/` directory
- **Advisory locks**: All sweep commands use advisory locks for safe concurrent execution

### Inconsistencies

- `delete_draft` (`ad_create.py:892`) does NOT use `storage_keys()` while every other deletion path does
- `cmd_cancel` (`ad_create.py:116-117`) only deletes from FSM `photos` list (originals only), not via `storage_keys()`
- `sweep_drafts.py:45` uses 30 minutes; `db-retention.md:32` says 7 days
