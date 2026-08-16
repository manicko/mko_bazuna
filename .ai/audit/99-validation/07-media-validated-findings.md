---
name: audit-validated-findings
description: Phase 07 Media Handling & Security validated findings
agent: validator
alwaysApply: false
---

# Phase 07 Audit Findings Validation — Media Handling & Security

**Validator:** validator
**Source:** .ai/audit/07-media/findings.md
**Output:** .ai/audit/99-validation/07-media-validated-findings.md
**Validated:** 2026-08-15
**Status:** complete

---

## Methodology

Each finding was validated against the **actual implementation** in `src/backend/apps/` and `src/telegram_bot/` (codebase root: `src/`). Validation criteria:

1. **Technical correctness** — is the problem real? (verified by code inspection across all cited files)
2. **Current applicability** — is the codebase still in this state? (verified by reading every cited file at its current line numbers)
3. **Architectural fit** — does the recommendation align with project patterns? (checked against docs/01-spec/technical-specification.md, docs/02-database/db-schema.md, and .kilo/commands/audit/phases/07-audit-media.md)
4. **Operational value** — is the fix worth the effort at this project scale? (assessed against Phase-07 severity taxonomy)

**Critical environment note — path prefix discrepancy:** All findings reference files as `apps/core/...`, `apps/ads/...`, `apps/media/...`, `apps/seed/...`, `telegram_bot/...` etc. The actual files live under a `src/` layout: `apps/` resolves to `src/backend/apps/` and `telegram_bot/` resolves to `src/telegram_bot/`. All cited files exist and match the described code; only the path prefix differs. Line numbers are accurate for the actual files. This does not affect finding validity but is noted for traceability.

All 8 findings were validated by direct code inspection. Every cited file, function, and line number was read and cross-checked against the implementation. No finding was rejected — all describe real problems. One merge was applied (MED-004 → MED-001).

---

## Runtime Verification (Validator-Executed)

Code inspection was performed against the live repository at src/. Key verification actions:

| Check | Method | Confirms |
|-------|--------|----------|
| Thumbnail fields never collected in sweeps | Read all 5 sweep commands + soft_delete_user_ads + delete_draft | MED-001, MED-004 |
| AdImage has no pre_delete signal or delete() override | Glob for signals.py in apps/ads/ (none exists); read AdImage class | MED-001 |
| delete_photo deletes single key only | Read src/telegram_bot/services/media.py:80-95 | MED-001 |
| Dedup return skips super().save() leaving file on disk | Read AdImage.save() at models.py:461-493 | MED-002 |
| Thumbnail gen runs before dedup-save in update_ad_and_moderate | Read ad_create.py:724-748 | MED-002 |
| No count guard before save_photo in process_photos | Read ad_create.py:358-412 | MED-003 |
| Misleading error message on 5+ photo overflow | Read ad_create.py:365-375 | MED-003 |
| No /media/ rate-limit zone in nginx | Read nginx.conf:61-67; grep for limit_req_zone across src/ and docker/ | MED-003 |
| ImageGenerator reuses seed/ keys across ads | Read src/backend/apps/seed/generators/images.py:158-171 | MED-004 |
| No orphan sweep command exists | Glob all management commands; grep for orphan/reconcile/sweep_media | MED-005 |
| EXIF tests only cover strip_photo_exif in isolation | Read test_media_security.py:289-331, test_media.py | MED-006 |
| _serve_image returns bare HttpResponse with no headers | Read listings.py:90-102 | MED-007 |
| AdImage.save() recomputes hash on any save with blank sha256 | Read models.py:469-477; seed backfill uses .update() | MED-008 |

---

## Findings

<!-- severity: CRITICAL -->

### MED-001: Thumbnail files never deleted on purge - orphaning (disk bloat) + PII-erasure gap

| Field | Value |
|-------|-------|
| **ID** | MED-001 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/core/management/commands/{delete_sweep,purge_rejected_ads,purge_failed_ads,sweep_drafts}.py, src/backend/apps/core/management/commands/consent_hard_delete.py, src/backend/apps/users/services/deletion.py (soft_delete_user_ads), src/telegram_bot/handlers/ad_create.py (delete_draft), src/telegram_bot/services/media.py (delete_photo), src/backend/apps/ads/models.py (AdImage) |
| **Classification** | mandatory |

**Description:** Every media-deletion path collects only the AdImage.image storage key and calls delete_photo(key) per key. The three thumbnail variants (thumbnail_small, thumbnail_medium, thumbnail_large) are never collected and never deleted, and AdImage defines no pre_delete signal or delete() override that removes files (so ORM CASCADE from Ad.delete() also leaves them). Two impacts follow:

1. Storage hygiene (disk bloat): every purged ad (archive/delete/reject/failed/draft sweeps) leaks 3 thumbnail files permanently - violates Phase-07 section 5(d) no orphaned files.
2. PII erasure (CRITICAL): consent_hard_delete (30-day hard-delete after withdrawal) removes the image keys but NOT the thumbnails. After a data subject withdraws consent, the user ad thumbnails remain on disk, violating Phase-07 section 4.6 / 5(f) referenced media files are physically removed, not just DB rows and section 7 edge-case 7 (reference-counted deletion).

**Evidence (validated - all cited locations confirmed at current line numbers):**

- src/backend/apps/core/management/commands/delete_sweep.py:63-76 - values_list(image, flat=True) then delete_photo(storage_key); only image.
- Same pattern in purge_rejected_ads.py:63-77, purge_failed_ads.py:62-75, sweep_drafts.py:61-74, consent_hard_delete.py:68-88 - all collect only image.
- src/backend/apps/users/services/deletion.py:238-252 - soft_delete_user_ads collects AdImage.objects.filter(ad_id__in=draft_ad_ids).values_list(image, flat=True) and calls delete_photo(storage_key) per key; no thumbnails.
- src/telegram_bot/handlers/ad_create.py:524-525 - delete_draft: for img in ad.images.all(): delete_photo(img.image) - only image.
- src/telegram_bot/services/media.py:80-95 - delete_photo deletes a single key; no thumbnail awareness.
- src/backend/apps/ads/models.py:402-493 - AdImage model: no pre_delete signal, no delete() override, no delete_files() method.
- No apps/ads/signals.py exists (glob confirms zero results in src/backend/apps/ads/).
- Repo-wide grep for any thumbnail-deletion logic across all sweep commands returns no matches for thumbnail_small/thumbnail_medium/thumbnail_large in any deletion context.

**Spec alignment:**

- Phase-07 audit template section 5(d) - no orphaned files (storage hygiene).
- Phase-07 audit template section 5(f) - PII-erasure cascade: referenced physical media, not only DB rows.
- Phase-07 audit template section 7 edge-case 7.94 - Two ads reference the same file (dedup) -> sweep uses reference counting, not premature delete.
- docs/02-database/db-schema.md:246-248 - documents thumbnail_small/medium/large fields but says nothing about their lifecycle on deletion.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Fully validated. Every sweep command, the consent-hard-delete command, soft_delete_user_ads, and delete_draft collect only the image field and call delete_photo(key) - the three thumbnail_* fields are never collected or deleted. No pre_delete signal or model-level deletion hook exists. Spec references Phase-07 5(d) and 5(f) and edge-case 7.94, all of which are violated by the current code.
> - **Merge:** MED-004 merged into this finding - both call for the same reference-counted AdImage.delete_files() helper. See merged-findings section below.
> - **Path note:** Finding references `apps/core/...` and `apps/ads/...` - actual paths are `src/backend/apps/core/...` and `src/backend/apps/ads/...` (same code, `src/` prefix).

**Recommendation:**
1. [Mandatory] Implement a central, reference-counted helper - AdImage.delete_files() - that deletes the image key plus all three thumbnail_* keys, deleting each file only when no other AdImage row still references it.
2. [Mandatory] Wire delete_files() into every sweep command, soft_delete_user_ads, delete_draft, and an AdImage.pre_delete signal so ORM cascades also clean up complete media.
3. [Doc-Update] Update docs/02-database/db-schema.md ad_images section to document the physical file deletion contract (reference-counted, includes thumbnails).

**Effort:** medium | **Priority:** mandatory (CRITICAL)

---

<!-- severity: MEDIUM -->

### MED-002: Hash dedup skips the DB row but leaves the duplicate physical file (and its thumbnails) on disk

| Field | Value |
|-------|-------|
| **ID** | MED-002 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/ads/models.py (AdImage.save), src/telegram_bot/handlers/ad_create.py (save_photo, update_ad_and_moderate), src/backend/apps/media/services/thumbnails.py (ThumbnailService) |
| **Classification** | mandatory |

**Description:** The spec (docs/01-spec/technical-specification.md:202) states photo dedup reuses existing storage: AdImage.save() computes the SHA-256 and, if the same user already has an image with that hash, returns early without calling super().save(), so no duplicate row is created. However, the file was already written to disk earlier in the pipeline by save_photo (bot photo-upload step), and the duplicate is never removed. Thumbnail generation in update_ad_and_moderate runs before the (possibly skipped) AdImage.save(), so the three thumbnail files for the duplicate are also written to disk and never cleaned up. Result: every duplicate upload leaks one original + up to 3 thumbnails permanently (no sweep references them).

**Evidence (validated - all cited locations confirmed):**

- src/telegram_bot/handlers/ad_create.py:580-608 - save_photo writes the file to disk via os.open(..., O_CREAT|O_EXCL) (line 594); file now exists on disk.
- src/telegram_bot/handlers/ad_create.py:724-730 - AdImage.objects.create(...) triggers AdImage.save().
- src/backend/apps/ads/models.py:486-491 - on duplicate sha256 for same user: if duplicate: return # Skip duplicate (no super().save(), no row, file left on disk).
- src/telegram_bot/handlers/ad_create.py:732-748 - thumbnail generation (ThumbnailService.generate_thumbnails) runs on the duplicate bytes (lines 738-741) and writes 3 files to disk regardless of whether the row persists.

The execution order is: save_photo writes original -> AdImage.objects.create() triggers save() which may return early (no DB row) -> thumbnail generation writes 3 more files -> ad_image.save() is called again on the unsaved instance and returns early again (still no DB row). Net result: 4 files leaked (1 original + 3 thumbnails) with no DB row referencing them.

**Spec alignment:**

- docs/01-spec/technical-specification.md:202 - Photo deduplication: If the same user already has an image with the same hash, the duplicate is skipped (reuses existing storage).
- Phase-07 section 5(d) - no orphaned files.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** The dedup-at-save behavior is confirmed. save_photo writes the file to disk before AdImage.save() is called, and AdImage.save() returns early on duplicate without creating a DB row. Thumbnail generation runs in the loop body between create() and the second save(), so 3 thumbnail files are also written for the duplicate. The orphan-sweep (MED-005) would be a backstop, but the recommendation to detect dedup before writing is the correct fix.
> - **Path note:** Finding references `apps/ads/models.py` and `apps/media/services/` - actual paths are `src/backend/apps/ads/models.py` and `src/backend/apps/media/services/`.

**Recommendation:**
1. [Mandatory] Detect dedup before writing at the upload step. In `save_photo` (`src/telegram_bot/handlers/ad_create.py:580-608`), after EXIF-stripping the bytes (line 592, `cleaned = strip_photo_exif(data)`) but before the atomic file write (line 594, `os.open` with `O_CREAT|O_EXCL`), compute the SHA-256 of the cleaned in-memory bytes. Add `FileHashService.calculate_sha256_from_bytes(data: bytes) -> str` to `hash_service.py` (the existing `calculate_sha256(file_path)` only reads from disk). Look up an existing `AdImage` by `sha256` + `ad__user_id`, using the same query pattern as `AdImage.save()` at `models.py:486-489`. If a match exists, return the existing `AdImage.image` storage key and discard the upload bytes -- no file is written to disk. If no match, proceed with the existing `os.open` write path. The `user_id` for the lookup is available from FSM state (`ad_create.py:60,478`) and must be passed into `save_photo`.
2. [Mandatory] Mitigate the TOCTOU race condition (concurrent identical uploads both passing the lookup) at the database level: add a `UniqueConstraint(fields=["sha256", "user"])` to `AdImage` -- this requires a `user` FK mirroring `ad.user` (a schema migration, per project rule 13). Under concurrent uploads, the first write creates the row; subsequent writes raise `IntegrityError`, caught by the caller to look up and reuse the existing `AdImage.image` key. This is preferred over `get_or_create` because it guarantees uniqueness at the storage-engine level.
3. [Recommended] With dedup-before-write in place, `AdImage.save()`'s dedup check (`models.py:480-491`) becomes defense-in-depth. Retain it as a backstop -- it will not match in the normal flow but protects against bypass paths (admin edits, seed import via `.update()`). See rollout note at line 458.

**Effort:** small | **Priority:** recommended (mandatory fix)

---

<!-- severity: MEDIUM -->

### MED-003: Photo count not enforced before disk write; no bot-side rate limit; misleading over-limit message

| Field | Value |
|-------|-------|
| **ID** | MED-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/telegram_bot/handlers/ad_create.py (process_photos, done-check), src/telegram_bot/schemas/message_payloads.py (PhotoCountPayload), docker/nginx/nginx.conf |
| **Classification** | mandatory |

**Description:** The 1 to 5 photo rule (spec decision E, docs/01-spec/technical-specification.md:71) is enforced only at the done checkpoint via PhotoCountPayload(ge=1, le=5), after every photo has already been downloaded and written to disk by save_photo in process_photos. There is no len(photos) >= 5 guard before accepting a new photo, so a seller (or a spam bot using a compromised account) can stream an unbounded number of files to MEDIA_ROOT in a single session. When the count exceeds 5, the done handler raises but prints a minimum-1 message (wrong reason) and does not clean up the excess on-disk files. There is also no rate limiting on bot uploads (or on /media/), so rapid spam is unbounded.

**Evidence (validated - all cited locations confirmed):**

- src/telegram_bot/handlers/ad_create.py:358-412 - process_photos: appends to photos and calls save_photo (line 402) with no len(photos) check.
- src/telegram_bot/handlers/ad_create.py:365-375 - done branch: PhotoCountPayload(photo_count=count) raises on >5; except Exception prints "Please send at least 1 photo (you have count)." - message asserts a minimum when the real failure is the maximum; excess files not cleaned up.
- Grep rate.?limit|throttl|RateLimit across src/ only finds apps/search/services/rate_limit.py (autocomplete) and nginx /login + /search zones; no bot-side or /media rate limiting.
- docker/nginx/nginx.conf:23-25,61-67 - limit_req_zone only defines login_limit and search_limit; /media/ has no zone.
- src/telegram_bot/schemas/message_payloads.py:41-47 - PhotoCountPayload.photo_count: Field(ge=1, le=5) confirms 1-5 range but only checked at done.

**Spec alignment:**

- docs/01-spec/technical-specification.md:71 - 1 to 5 photos per ad (decision E).
- docs/01-spec/technical-specification.md:73 - <= 5 photos / 10 MB per ad.
- Phase-07 section 5(b) - Upload validation: Type, size, dimensions, count 1-5, and rate limits enforced.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Code inspection confirms: (1) no len(photos) guard in process_photos before writing - each photo is persisted to disk via save_photo immediately upon receipt; (2) the done handler error message ("Please send at least 1 photo") is misleading when the actual failure is exceeding the 5-photo maximum; (3) no bot-side rate limiting on photo uploads, and nginx has no /media/ rate-limit zone. PhotoCountPayload schema (ge=1, le=5) is only called at the done checkpoint.
> - **Path note:** Finding references apps/ paths - actual code at src/telegram_bot/... and docker/nginx/nginx.conf confirmed.

**Recommendation:**
1. [Mandatory] Enforce len(photos) >= 5 in process_photos and reject the 6th photo with a Maximum 5 photos message.
2. [Recommended] When PhotoCountPayload rejects, delete the excess on-disk files already stored in FSM state.
3. [Recommended] Add per-user/per-chat upload throttling in the bot and/or an nginx /media rate zone.

**Effort:** small | **Priority:** recommended (mandatory fix)

---
<!-- severity: MEDIUM -->

### MED-004: Seed data shares image keys across ads but dedup/sweep logic assumes per-row ownership (reference-count gap) [MERGED into MED-001]

> **Validation Note:**
> - **Action:** merged
> - **Detail:** Root cause is identical to MED-001: deletion paths collect only AdImage.image and call delete_photo(key) without reference counting. MED-001's recommended solution (reference-counted AdImage.delete_files() helper) resolves both the thumbnail-orphaning issue (MED-001) and the shared-key premature-delete issue (MED-004). The findings are merged; this content retained for reference. Fix is captured under MED-001.
> - **See also:** MED-001 (merge target)
> - **Path note:** Finding references apps/ - actual paths are src/backend/apps/....

| Field | Value |
|-------|-------|
| **ID** | MED-004 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/backend/apps/seed/generators/images.py (ImageGenerator.generate, _thumbnail_key), src/backend/apps/core/management/commands/{delete_sweep,sweep_drafts,purge_rejected_ads,purge_failed_ads,consent_hard_delete}.py, src/backend/apps/ads/models.py (AdImage) |
| **Classification** | mandatory |
| **Status** | MERGED into MED-001 |

**Description:** Seed data (ImageGenerator, images.py:158-171) deliberately reuses the same seed/filename storage key across multiple ads, and the same filename-thumbnails across those AdImage rows (via _thumbnail_key). The spec (technical-specification.md:144) says thumbnail keys stored alongside originals and originals preserved; thumbnails are additive. However, the sweep commands (delete_sweep, sweep_drafts, etc.) collect AdImage.image values per-ad and call delete_photo(key) for each, with no reference counting. If even one of the sharing ads is swept, the shared thumbnail file is deleted from disk while other ads still reference it — breaking image thumbnails for surviving seed ads. The spec (section 7 edge-case 7.94: Two ads reference the same file (dedup) sweep uses reference counting, not premature delete) explicitly calls for reference counting, but no such logic exists. The same gap applies to bot-uploaded dedup duplicates (MED-002): a shared original could be deleted while another AdImage row still references it.

**Evidence (validated - all cited locations confirmed):**

- src/backend/apps/core/management/commands/delete_sweep.py:63-76 - values_list(image, flat=True) per ad, then delete_photo(key) per key; no count of referencing rows.
- Same pattern in sweep_drafts.py:61-74, purge_rejected_ads.py:63-77, purge_failed_ads.py:62-75, consent_hard_delete.py:68-88.
- src/backend/apps/seed/generators/images.py:158-171 - ImageGenerator.generate() creates AdImage records with shared keys (seed/filename) across multiple ads; _thumbnail_key reuses seed/stem-size.jpg.
- src/backend/apps/ads/views/listings.py:142-154 - media_gate already uses filter (not get) to handle shared keys gracefully at read time, but the deletion path has no equivalent guard.
- AdImage has no pre_delete signal and no reference-counting delete method.

**Recommendation (merged into MED-001):** Implement reference-counted physical deletion in the AdImage.delete_files() helper: before delete_photo(key), query AdImage.objects.filter(image=key).count() (and similarly for each thumbnail_* field); delete the file only when the count is 1 or less (i.e., the current row is the last reference). Centralize this in the AdImage.delete_files() helper (see MED-001).

**Effort:** covered by MED-001 | **Priority:** recommended (mandatory fix)

---

<!-- severity: MEDIUM -->

### MED-005: Seed media directory cleaned wholesale but no orphan sweep exists for production bot-uploaded files

| Field | Value |
|-------|-------|
| **ID** | MED-005 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/seed/services/seed_service.py (_clean), src/backend/apps/media/, src/backend/apps/core/management/commands/ |
| **Classification** | advisory |

**Description:** Seed data cleanup (seed_service.py:210-218) does shutil.rmtree(seed_dir, ignore_errors=True) — a brute-force wipe of MEDIA_ROOT/seed/. This works for the dev-only seed volume but masks a systemic gap: there is no orphan-sweep management command for production. MED-001/MED-002/MED-004 establish that orphaned files can accumulate (orphaned thumbnails, duplicate-upload leaks, shared-key premature-deletes). Without a periodic sweep_orphaned_media job, MEDIA_ROOT grows unbounded in production. The Phase-07 audit section 5(d) no orphaned files requires a store/DB diff; no such job exists.

**Evidence (validated - all cited locations confirmed):**

- src/backend/apps/seed/services/seed_service.py:210-218 - shutil.rmtree(seed_dir, ignore_errors=True) for seed cleanup only (wipes MEDIA_ROOT/seed/ directory).
- Grep for orphan|sweep_media|reconcile_media across all management commands only finds sweep commands for ads (status-based), no media-reconciliation job.
- No apps/media/management/commands/orphan_sweep.py or similar exists (confirmed by directory listing of src/backend/apps/media/management/commands/ - only __init__.py and backfill_thumbnails.py exist).

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed: seed cleanup only wipes MEDIA_ROOT/seed/ via shutil.rmtree. No orphan-sweep command exists anywhere in the codebase. The apps/media/management/commands/ directory contains only backfill_thumbnails.py (generates missing thumbnails) and __init__.py. Phase-07 section 5(d) requires a store/DB diff to assert no orphaned files - no such job exists. This is a valid advisory finding (no immediate crash, but production disk bloat risk).
> - **Path note:** Finding references _clean_seed_data at line 210-218 - the method is _clean at line 175, with the shutil.rmtree call at line 217. Line range approximately correct.

**Recommendation:**
1. [Recommended] Add a periodic sweep_orphaned_media management command that diffs MEDIA_ROOT contents against all AdImage.image/thumbnail_* DB values and deletes unreferenced files.
2. [Recommended] Run via cron alongside the retention sweeps.

**Effort:** medium | **Priority:** recommended

---
<!-- severity: LOW -->

### MED-006: EXIF stripping not verified on the full upload pipeline — test gap

| Field | Value |
|-------|-------|
| **ID** | MED-006 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | src/telegram_bot/handlers/ad_create.py (save_photo), src/telegram_bot/services/media.py (strip_photo_exif), src/telegram_bot/tests/test_media.py, src/backend/apps/ads/tests/test_media_security.py |
| **Classification** | mandatory |

**Description:** The Phase-07 section 5(c) audit requires verifying via exiftool that EXIF/metadata is stripped from stored image bytes. save_photo (ad_create.py:592) does call strip_photo_exif (media.py:98-116) which opens the image, applies exif_transpose, pops the exif info, and re-encodes. This is correct. However, the test suite (test_media_security.py) tests strip_photo_exif in isolation but does not test the full upload path — i.e., that an EXIF-bearing JPEG uploaded through the bot handler is actually stored stripped on disk. test_media.py tests validate_photo only (format/size/dimensions), not EXIF stripping of the persisted file. This leaves a verification gap: a regression in save_photo that bypasses strip_photo_exif would leak EXIF/PII with no test guard.

**Evidence (validated - all cited locations confirmed):**

- src/telegram_bot/handlers/ad_create.py:592 - cleaned = strip_photo_exif(data) inside _write, called by save_photo (ad_create.py:604). Implementation is correct.
- src/backend/apps/ads/tests/test_media_security.py:289-331 - TestExifStripping class with 5 tests (test_strip_photo_exif_removes_make, _removes_model, _removes_gps, _preserves_image, _valid_jpeg). All test strip_photo_exif directly — none call save_photo or verify the on-disk file after the upload pipeline.
- src/telegram_bot/tests/test_media.py - tests validate_jpeg_bytes, validate_photo (format/size/dimensions), generate_storage_key (UUID format). No EXIF-stripping test.
- No test in either file calls save_photo() and then asserts the persisted on-disk file has no EXIF metadata.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** The strip_photo_exif implementation is correct — it is called in save_photo._write before the file is written to disk. The finding is not about an implementation bug but about a test-coverage gap: Phase-07 section 5(c) requires verification evidence (exiftool shows no residual metadata), but no integration test verifies the full upload pipeline. If save_photo were refactored to bypass strip_photo_exif, no test would catch it.
> - **Classification note:** Type is SPEC-DEVIATION — the audit phase requires verification evidence which is missing. The implementation itself is correct. Lowest-severity finding.
> - **Path note:** Finding references backend/apps/ads/tests/ and telegram_bot/tests/ - actual paths are src/backend/apps/ads/tests/ and src/telegram_bot/tests/.

**Recommendation:**
1. [Low-priority mandatory] Add an integration test that calls save_photo with an EXIF-bearing JPEG, then verifies via exiftool or PIL that the persisted on-disk file has no EXIF metadata.

**Effort:** small | **Priority:** recommended (test coverage)

---

<!-- severity: LOW -->

### MED-007: DEBUG-mode media serving bypasses nginx security headers

| Field | Value |
|-------|-------|
| **ID** | MED-007 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/ads/views/listings.py (_serve_image, media_gate) |
| **Classification** | advisory |

**Description:** In production (DEBUG=False), media_gate returns an X-Accel-Redirect header and nginx applies Content-Security-Policy, X-Frame-Options: DENY, X-Content-Type-Options: nosniff, and MIME whitelisting (image/jpeg only) via the /protected-media/ location. But in DEBUG mode (DEBUG=True), _serve_image (listings.py:90-102) serves files via HttpResponse(data, content_type=image/jpeg) with none of the nginx security headers (no CSP, no X-Frame-Options, no nosniff, no Content-Disposition). This dev-mode path could be accidentally used in a staging environment with DEBUG=True, exposing images without the hardening the spec requires (db-schema.md:254-255: X-Content-Type-Options: nosniff, whitelists image/jpeg).

**Evidence (validated - all cited locations confirmed):**

- src/backend/apps/ads/views/listings.py:90-102 - _serve_image: return HttpResponse(data, content_type="image/jpeg") - no security headers set.
- src/backend/apps/ads/views/listings.py:158-162 - media_gate DEBUG branch (staff): if settings.DEBUG: return _serve_image(image_key) - calls _serve_image directly.
- src/backend/apps/ads/views/listings.py:170-171 - media_gate DEBUG branch (non-staff): if settings.DEBUG: return _serve_image(image_key) - same.
- docker/nginx/nginx.conf:74-84 - /protected-media/ location has X-Content-Type-Options nosniff, Content-Disposition inline, X-Frame-Options DENY, Content-Security-Policy. Production path is hardened.
- docker/nginx/nginx.conf:37-40 - server-level add_header for Strict-Transport-Security, X-Content-Type-Options nosniff, X-Frame-Options DENY (applied by nginx to all proxied responses, but NOT Content-Security-Policy which is only in /protected-media/).
- docs/02-database/db-schema.md:254-255 - specifies X-Content-Type-Options: nosniff and image/jpeg whitelist.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** _serve_image returns a bare HttpResponse(data, content_type="image/jpeg") with no CSP, X-Frame-Options, X-Content-Type-Options, or Content-Disposition headers. In production, nginx /protected-media/ location adds all four. In DEBUG mode, if served directly by Django (e.g., runserver without nginx), none are present. Even with nginx in front, server-level add_header only covers HSTS, X-Content-Type-Options, and X-Frame-Options - CSP and Content-Disposition are missing (they are in the /protected-media/ location only). Dev/staging hardening gap, low severity.
> - **Path note:** Finding references apps/ads/views/listings.py - actual path is src/backend/apps/ads/views/listings.py.

**Recommendation:**
1. [Recommended] Add the same security headers (Content-Security-Policy, X-Frame-Options: DENY, X-Content-Type-Options: nosniff, Content-Disposition: inline) to the DEBUG-mode _serve_image response, so the dev path matches production nginx hardening.

**Effort:** trivial | **Priority:** recommended

---
<!-- severity: LOW -->

### MED-008: AdImage.save() recomputes SHA-256 on every save where sha256 is blank

| Field | Value |
|-------|-------|
| **ID** | MED-008 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | src/backend/apps/ads/models.py (AdImage.save, line 461-493), src/backend/apps/media/services/hash_service.py (FileHashService) |
| **Classification** | advisory |

**Description:** AdImage.save() (models.py:461-493) computes SHA-256 on every call where self._state.adding or not self.sha256. The second condition means that any save of an existing AdImage with a blank sha256 recomputes the hash by reading the file from disk. In the normal bot flow, AdImage.objects.create() (line 725) fires save() once (creating with _state.adding=True), then ad_image.save() (line 746) is called again to persist the thumbnail keys — at this point _state.adding is False but sha256 is populated, so the recompute is skipped. However, edge cases (e.g. bulk_update, admin edits, or any code path that saves an existing AdImage with an empty sha256) would trigger an unnecessary full file read + SHA-256 computation. The backfill job (seed_service.py:271-288) correctly uses update() to bypass this, but the model-level logic is fragile: it should compute the hash only when the file field is first set, not on every save where sha256 happens to be blank.

**Evidence (validated - all cited locations confirmed):**

- src/backend/apps/ads/models.py:469 - if self._state.adding or not self.sha256: enters the hash-computation block on any save where sha256 is empty, regardless of whether the image field changed.
- src/backend/apps/ads/models.py:477 - file_hash = FileHashService.calculate_sha256(file_path) reads the entire file from disk.
- src/backend/apps/seed/services/seed_service.py:288 - AdImage.objects.filter(pk=pk).update(sha256=file_hash) bypasses save() to avoid this; the model-level workaround is a code smell.

**Normal flow analysis:** In the bot flow (ad_create.py:724-746), AdImage.objects.create() calls save() with _state.adding=True. The hash is computed, and if not a duplicate, super().save() persists the row with sha256 populated. Then ad_image.save() (line 746) is called to update thumbnail keys. At this point _state.adding=False but sha256 is populated, so the recompute block is skipped. The finding only affects edge cases (admin edits, bulk_update, or any future code that saves an existing AdImage with blank sha256).

> **Validation Note:**
> - **Action:** validated
> - **Detail:** The or not self.sha256 condition at models.py:469 is confirmed. In the normal bot flow this is harmless (sha256 is populated after create(), so the second save() skips recompute). But it is fragile: any code path that calls save() on an existing AdImage with blank sha256 (e.g., admin editing the image field, or bulk_update without update_fields) triggers a full file read + SHA-256 computation. The seed backfill using .update() to bypass save() confirms the team is already aware and working around it. The spec (db-schema.md:244) says "auto-computed on save" without specifying the condition.
> - **Path note:** Finding references apps/ads/models.py and apps/media/services/hash_service.py - actual paths are src/backend/apps/ads/models.py and src/backend/apps/media/services/hash_service.py.

**Recommendation:**
1. [Recommended] Compute SHA-256 only when the image field has changed (track via self._original_image or compare against the DB value); move the dedup check to fire only when _state.adding is True.
2. [Recommended] Update docs/02-database/db-schema.md:244 to note that sha256 is computed on first save only (not re-computed on every save).

**Effort:** small | **Priority:** recommended

---
## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 (MED-001) |
| HIGH | 1 (MED-003) |
| MEDIUM | 3 (MED-002, MED-004 [merged], MED-005) |
| LOW | 2 (MED-006, MED-007) |
| ADVISORY | 1 (MED-008) |
| **Total findings** | **8** |
| **Rejected** | **0** |
| **Merged** | **1** (MED-004 -> MED-001) |

### Validation Summary Table

| Finding | Status | Evidence Quality | Type | Priority |
|---------|--------|-----------------|------|----------|
| MED-001 | **validated** | High (8 cited locations, all confirmed) | SPEC-DEVIATION | mandatory (CRITICAL) |
| MED-002 | **validated** | High (4 cited locations, all confirmed) | SPEC-DEVIATION | mandatory |
| MED-003 | **validated** | High (5 cited locations, code + grep + nginx.conf) | SPEC-DEVIATION | mandatory |
| MED-004 | **validated (merged -> MED-001)** | High (5 cited locations, all confirmed) | SPEC-DEVIATION | covered by MED-001 |
| MED-005 | **validated** | High (2 cited locations, directory listing) | BEST-PRACTICE | recommended |
| MED-006 | **validated** | High (3 cited locations, all confirmed) | SPEC-DEVIATION | recommended |
| MED-007 | **validated** | High (5 cited locations, code + nginx.conf) | BEST-PRACTICE | recommended |
| MED-008 | **validated** | High (3 cited locations, all confirmed) | BEST-PRACTICE | recommended |

### Rejected Findings

None. All 8 findings describe real problems confirmed by code inspection.

### Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-------------|----------|
| MED-004 | MED-001 | Both address the same root cause: deletion paths collect only AdImage.image and call delete_photo(key) without reference counting. MED-001's recommended solution (reference-counted AdImage.delete_files()) resolves both the thumbnail-orphaning issue (MED-001) and the shared-key premature-delete issue (MED-004). MED-001's own recommendation explicitly states it also fixes the shared-key premature-delete of MED-004. |

### Reclassified Findings

None. All findings retain their original type classifications.

---

## Cross-Finding Dependency Graph

```
MED-001 (thumbnail deletion + PII erasure)
  |-- MED-004 (reference counting for shared keys) [merged into MED-001]
  |-- MED-002 (duplicate file leak -- backstop by orphan sweep)
  |-- MED-005 (orphan sweep -- backstop for MED-001, MED-002, MED-004 leaks)

MED-002 (dedup-before-write)
  |-- Depends on same AdImage.save() logic critiqued by MED-008

MED-003 (count enforcement + rate limiting)
  |-- Independent of MED-001-002

MED-006 (EXIF test gap)
  |-- Independent -- tests strip_photo_exif called from MED-002's save_photo

MED-007 (DEBUG-mode headers)
  |-- Independent of all other findings

MED-008 (SHA-256 recompute)
  |-- Related to MED-002 (dedup relies on sha256 computation in save())
```

**Key insight:** MED-001 is the **root cause** for 2 findings. The reference-counted `AdImage.delete_files()` helper recommended in MED-001 simultaneously resolves:
- Thumbnail orphaning on every sweep (MED-001)
- Shared-key premature deletion (MED-004, merged)
- The pre_delete signal gap (covers ORM CASCADE paths that MED-001 documents)

MED-005 (orphan sweep) is a defense-in-depth backstop for all file-leak findings (MED-001, MED-002, MED-004).

---

## Rollout Analysis

### Sequence recommended (highest-risk first):

| Step | Action | Blocked by | Risk |
|------|--------|-----------|------|
| 1 | MED-002: Detect dedup before write (compute SHA-256 from in-memory bytes at upload, look up by (user, sha256) before save_photo) + add UniqueConstraint(user, sha256) | none | Medium - changes upload flow + 1 schema migration (unique constraint on new user FK); race condition mitigated by DB-level constraint |
| 2 | MED-001 + MED-004: Implement AdImage.delete_files() with reference counting + pre_delete signal | none | Medium - new signal handler; must not break bulk_create in seed (seed uses bulk_create, not save()) |
| 3 | MED-003: Enforce count before write + fix misleading message + cleanup excess files | none | Low - guard before save_photo |
| 4 | MED-008: Refactor AdImage.save() to compute SHA-256 only when image field changes | MED-002 (if dedup-at-upload changes the save flow) | Low - code-only, no schema change |
| 5 | MED-005: Add sweep_orphaned_media management command | none | Low - new additive command |
| 6 | MED-007: Add security headers to DEBUG-mode _serve_image | none | Trivial - header additions |
| 7 | MED-006: Add integration test for EXIF stripping through save_photo | none | Low - test only |

### Key rollout considerations:

- **Two-process architecture (web + bot):** Per docs/99-agent/architecture.md, both share one DB; migrations run once before both start. Steps 1-3 and 5-7 are code-only changes; Step 1 additionally includes a schema migration for the unique constraint (runs before both processes start). Both processes can be restarted independently after deployment.
- **MED-002 risk:** Changing dedup to write-time lookup requires computing SHA-256 before calling save_photo. This means the bot must compute the hash of the downloaded photo bytes, check the DB, and only write if no existing row is found. Race condition: two identical uploads from the same user in parallel -- use get_or_create or a unique constraint on (user, sha256) to guarantee correctness.
- **MED-001 signal safety:** Adding an AdImage.pre_delete signal is backward-compatible. The signal handler must be careful with bulk_create (used by seed_service) -- pre_delete fires on .delete() calls, not bulk_create, so seed data is safe.
- **Backward compatibility:** All changes are backward-compatible with existing data. MED-002 adds one schema migration (unique constraint + user FK); existing AdImage rows get user populated via migration default from ad__user.
- **Rollback feasibility:** Changes are code + 1 schema migration (MED-002 unique constraint). Rollback = revert PR + run `migrate backward` to drop the constraint + restart both web and bot processes.

### Warnings

1. **MED-002 implementation order:** Must be implemented before or alongside MED-001 to avoid leaving the duplicate file leak unfixed while deploying thumbnail cleanup (the orphan sweep (MED-005) would catch MED-002 leaks, but fixing the source is preferable).
2. **MED-001 signal + MED-002 dedup:** If MED-002 is fixed (dedup before write), the AdImage.save() dedup check at models.py:486-491 becomes dead code (no duplicate rows will ever reach save). Consider removing or keeping as defense-in-depth.
3. **MED-008 + MED-002 interaction:** MED-002 proposed fix (computing SHA-256 before write) changes the flow that MED-008 critiques. If MED-002 moves hash computation to the upload step, MED-008 proposed save() refactor could be simplified or removed. Plan these together.

---

## Required Fixes

1. **MED-001 (CRITICAL):** Implement reference-counted AdImage.delete_files() that deletes image + all thumbnail_* keys only when the last referencing row is removed. Wire into all sweep commands, soft_delete_user_ads, delete_draft, and an AdImage.pre_delete signal. **Required for both disk hygiene (Phase-07 5d) and PII erasure (Phase-07 5f).**
2. **MED-002 (MEDIUM):** Detect duplicate upload before writing the file -- compute SHA-256 from in-memory bytes at upload time and look up an existing AdImage by (user, sha256) prior to save_photo. Add `FileHashService.calculate_sha256_from_bytes()`. Mitigate the TOCTOU race with a `UniqueConstraint(fields=["sha256", "user"])` on AdImage (requires a user FK, schema migration). Prevents file and thumbnail leaks at the source.
3. **MED-003 (HIGH):** Enforce len(photos) >= 5 in process_photos before accepting a 6th photo; fix the misleading error message; clean up excess on-disk files when count is rejected.

---

## Advisory Recommendations

1. **MED-005:** Add a periodic sweep_orphaned_media management command that diffs MEDIA_ROOT contents against all AdImage.image/thumbnail_* DB values and deletes unreferenced files.
2. **MED-007:** Add Content-Security-Policy, X-Frame-Options: DENY, X-Content-Type-Options: nosniff, and Content-Disposition: inline headers to the DEBUG-mode _serve_image response.
3. **MED-008:** Refactor AdImage.save() to compute SHA-256 only when the image field is newly set (detecting field change), not on every save where sha256 is blank.

---

*Validation conducted against Phase 07 Media Handling and Security phase template (.kilo/commands/audit/phases/07-audit-media.md).*
*All 8 findings confirmed as real problems via direct code inspection. 1 merge applied (MED-004 -> MED-001).*
