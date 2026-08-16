# Phase 07 Audit Findings — Media Handling & Security

**Executor:** audit-executor
**Template:** .kilo/commands/audit/phases/07-audit-media.md
**Status:** complete
**Validated:** yes

---

## Findings

### MED-001: Thumbnail files never deleted on purge — orphaning (disk bloat) + PII-erasure gap

| Field | Value |
|-------|-------|
| **ID** | MED-001 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | apps/core/management/commands/{delete_sweep,purge_rejected_ads,purge_failed_ads,sweep_drafts}.py, apps/core/management/commands/consent_hard_delete.py, apps/users/services/deletion.py (soft_delete_user_ads), telegram_bot/handlers/ad_create.py (delete_draft), telegram_bot/services/media.py (delete_photo), apps/ads/models.py (AdImage) |
| **Classification** | mandatory |

**Description:** Every media-deletion path collects only the AdImage.image storage key and calls delete_photo(key) per key. The three thumbnail variants (thumbnail_small, thumbnail_medium, thumbnail_large) are never collected and never deleted, and AdImage defines no pre_delete signal or delete() override that removes files (so ORM CASCADE from Ad.delete() also leaves them). Two impacts follow:

1. Storage hygiene (disk bloat): every purged ad (archive/delete/reject/failed/draft sweeps) leaks 3 thumbnail files permanently — violates Phase-07 section 5(d) no orphaned files.
2. PII erasure (CRITICAL): consent_hard_delete (30-day hard-delete after withdrawal) removes the image keys but NOT the thumbnails. After a data subject withdraws consent, the user ad thumbnails remain on disk, violating Phase-07 section 4.6 / 5(f) referenced media files are physically removed, not just DB rows and section 7 edge-case 7 (reference-counted deletion).

**Evidence:**
- delete_sweep.py:64-76 — values_list(image, flat=True) then delete_photo(storage_key); only image.
- Same in purge_rejected_ads.py:63-77, purge_failed_ads.py:62-75, sweep_drafts.py:61-74, consent_hard_delete.py:68-88, and soft_delete_user_ads (deletion.py:238-252); delete_draft (ad_create.py:524-525) iterates img.image only.
- delete_photo (media.py:80-95) deletes a single key; no thumbnail awareness.
- Repo-wide grep for any thumbnail-deletion logic returns no matches.
- AdImage model (models.py:402-519) has no pre_delete signal, no delete() override, no delete_files() method. No apps/ads/signals.py exists.

**Recommendation:** Introduce one central, reference-counted helper — delete_ad_image_files(ad_image) / AdImage.delete_files() — that deletes image plus all three thumbnail_* keys, deleting each only when no other AdImage row still references it (this also fixes the shared-key premature-delete of MED-004). Invoke it from every sweep, from the consent_hard_delete/soft_delete_user_ads loops, from delete_draft, and from an AdImage.pre_delete signal so ORM cascades also clean up complete media. Effort: medium. Priority: recommended (mandatory fix).

---

### MED-002: Hash dedup skips the DB row but leaves the duplicate physical file (and its thumbnails) on disk

| Field | Value |
|-------|-------|
| **ID** | MED-002 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | apps/ads/models.py (AdImage.save), telegram_bot/handlers/ad_create.py (save_photo, update_ad_and_moderate), apps/media/services/thumbnails.py (ThumbnailService) |
| **Classification** | mandatory |

**Description:** The spec (spec-index, technical-specification.md:202) states photo dedup reuses existing storage: AdImage.save() computes the SHA-256 and, if the same user already has an image with that hash, returns early without calling super().save(), so no duplicate row is created. However, the file was already written to disk earlier in the pipeline by save_photo (bot photo-upload step), and the duplicate is never removed. Thumbnail generation in update_ad_and_moderate runs before the (possibly skipped) AdImage.save(), so the three thumbnail files for the duplicate are also written to disk and never cleaned up. Result: every duplicate upload leaks one original + up to 3 thumbnails permanently (no sweep references them).

**Evidence:**
- ad_create.py:580-608 save_photo writes the file to disk via os.open(..., O_CREAT|O_EXCL) and returns the key; file now exists on disk.
- ad_create.py:724-730 AdImage.objects.create(...) triggers AdImage.save().
- models.py:486-491 — on duplicate sha256 for same user: if duplicate: return  # Skip duplicate (no super().save(), no row, file left on disk).
- ad_create.py:732-748 thumbnail generation (ThumbnailService.generate_thumbnails) runs on the duplicate bytes and writes 3 files regardless of whether the row persists.

**Recommendation:** Detect dedup before writing: compute the SHA-256 during upload, look up an existing AdImage by (user, sha256), and only write the file if no match exists — otherwise reuse the existing key and discard the upload bytes. Alternatively, when dedup is detected inside AdImage.save(), delete the just-written duplicate file (and any generated thumbnails). Effort: small. Priority: recommended (mandatory fix).

---

### MED-003: Photo count not enforced before disk write; no bot-side rate limit; misleading over-limit message

| Field | Value |
|-------|-------|
| **ID** | MED-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | telegram_bot/handlers/ad_create.py (process_photos, done-check), telegram_bot/schemas/message_payloads.py (PhotoCountPayload), docker/nginx/nginx.conf |
| **Classification** | mandatory |

**Description:** The 1 to 5 photo rule (spec decision E: 1 to 5 photos, technical-specification.md:71) is enforced only at the done checkpoint via PhotoCountPayload(ge=1, le=5), after every photo has already been downloaded and written to disk by save_photo in process_photos. There is no len(photos) >= 5 guard before accepting a new photo, so a seller (or a spam bot using a compromised account) can stream an unbounded number of files to MEDIA_ROOT in a single session. When the count exceeds 5, the done handler raises but prints Please send at least 1 photo (wrong reason) and does not clean up the excess on-disk files. There is also no rate limiting on bot uploads (or on /media/), so rapid spam is unbounded.

**Evidence:**
- ad_create.py:358-412 process_photos: appends to photos and calls save_photo(...) (line 402) with no len(photos) check.
- ad_create.py:365-375 done branch: PhotoCountPayload(photo_count=count) raises on >5; except Exception: await message.answer(f Please send at least 1 photo (you have {count}).) — message asserts a minimum when the real failure is the maximum; excess files not cleaned up.
- Grep rate.?limit|throttl|RateLimit across src/ only finds apps/search/services/rate_limit.py (autocomplete) and nginx /login + /search zones; no bot-side or /media rate limiting.
- nginx.conf:23-25,61-67 limit_req_zone only defines login_limit and search_limit; /media/ has no zone.

**Recommendation:** (a) enforce len(photos) >= 5 in process_photos and reject the 6th photo with a correct maximum 5 photos message; (b) when PhotoCountPayload rejects, delete the excess on-disk files already stored in the FSM state; (c) add per-user/per-chat upload throttling in the bot (and/or an nginx /media rate zone). Effort: small. Priority: recommended (mandatory fix).

---

### MED-004: Seed data shares image keys across ads but dedup/sweep logic assumes per-row ownership (reference-count gap)

| Field | Value |
|-------|-------|
| **ID** | MED-004 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | apps/seed/generators/images.py (ImageGenerator.generate, _thumbnail_key), apps/core/management/commands/{delete_sweep,sweep_drafts,purge_rejected_ads,purge_failed_ads,consent_hard_delete}.py, apps/ads/models.py (AdImage) |
| **Classification** | mandatory |

**Description:** Seed data (ImageGenerator, images.py:158-171) deliberately reuses the same seed/filename storage key across multiple ads, and the same filename-thumbnails across those AdImage rows (via _thumbnail_key). The spec (technical-specification.md:144) says thumbnail keys stored alongside originals and originals preserved; thumbnails are additive. However, the sweep commands (delete_sweep, sweep_drafts, etc.) collect AdImage.image values per-ad and call delete_photo(key) for each, with no reference counting. If even one of the sharing ads is swept, the shared thumbnail file is deleted from disk while other ads still reference it — breaking image thumbnails for surviving seed ads. The spec (section 7 edge-case 94: Two ads reference the same file (dedup) sweep uses reference counting, not premature delete) explicitly calls for reference counting, but no such logic exists. The same gap applies to bot-uploaded dedup duplicates (MED-002): a shared original could be deleted while another AdImage row still references it.

**Evidence:**
- delete_sweep.py:63-76 — values_list(image, flat=True) per ad, then delete_photo(key) per key; no count of referencing rows.
- Same pattern in sweep_drafts.py:61-74, purge_rejected_ads.py:63-77, purge_failed_ads.py:62-75, consent_hard_delete.py:68-88, soft_delete_user_ads (deletion.py:238-252).
- media_gate (listings.py:142-154) already uses filter (not get) to handle shared keys gracefully at read time, but the deletion path has no equivalent guard.
- AdImage has no pre_delete signal and no reference-counting delete method.

**Recommendation:** Implement reference-counted physical deletion: before delete_photo(key), query AdImage.objects.filter(image=key).count() (and similarly for each thumbnail_* field); delete the file only when the count is 1 or less (i.e., the current row is the last reference). Centralize this in the AdImage.delete_files() helper (see MED-001). Effort: medium. Priority: recommended (mandatory fix).

---

### MED-005: Seed media directory cleaned wholesale but no orphan sweep exists for production bot-uploaded files

| Field | Value |
|-------|-------|
| **ID** | MED-005 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | apps/seed/services/seed_service.py (_clean_seed_data, line 210-218), apps/media/, apps/core/management/commands/ |
| **Classification** | advisory |

**Description:** Seed data cleanup (seed_service.py:210-218) does shutil.rmtree(seed_dir) — a brute-force wipe of MEDIA_ROOT/seed/. This works for the dev-only seed volume but masks a systemic gap: there is no orphan-sweep management command for production. MED-001/MED-002/MED-004 establish that orphaned files can accumulate (orphaned thumbnails, duplicate-upload leaks, shared-key premature-deletes). Without a periodic sweep_orphaned_media job, MEDIA_ROOT grows unbounded in production. The Phase-07 audit section 5(d) no orphaned files requires a store/DB diff; no such job exists.

**Evidence:**
- seed_service.py:210-218 — shutil.rmtree(seed_dir, ignore_errors=True) for seed cleanup only.
- Grep for orphan|sweep_media|reconcile_media across management commands only finds sweep commands for ads (status-based), no media-reconciliation job.
- No apps/media/management/commands/orphan_sweep.py or similar exists.

**Recommendation:** Add a periodic sweep_orphaned_media management command that diffs MEDIA_ROOT contents against all AdImage.image/thumbnail_* DB values and deletes unreferenced files. Run via cron alongside the retention sweeps. Effort: medium. Priority: recommended.

---

### MED-006: EXIF stripping not verified on the full upload pipeline — test gap

| Field | Value |
|-------|-------|
| **ID** | MED-006 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | telegram_bot/handlers/ad_create.py (save_photo), telegram_bot/services/media.py (strip_photo_exif), telegram_bot/tests/test_media.py, backend/apps/ads/tests/test_media_security.py |
| **Classification** | mandatory |

**Description:** The Phase-07 section 5(c) audit requires verifying via exiftool that EXIF/metadata is stripped from stored image bytes. save_photo (ad_create.py:592) does call strip_photo_exif (media.py:98-116) which opens the image, applies exif_transpose, pops the exif info, and re-encodes. This is correct. However, the test suite (test_media_security.py) tests strip_photo_exif in isolation but does not test the full upload path — i.e., that an EXIF-bearing JPEG uploaded through the bot handler is actually stored stripped on disk. test_media.py tests validate_photo only (format/size/dimensions), not EXIF stripping of the persisted file. This leaves a verification gap: a regression in save_photo that bypasses strip_photo_exif would leak EXIF/PII with no test guard.

**Evidence:**
- ad_create.py:592 — cleaned = strip_photo_exif(data) inside _write, called by save_photo (ad_create.py:604).
- test_media_security.py:289-331 TestExifStripping — unit-tests strip_photo_exif function only, does not verify the on-disk file after save_photo.
- test_media.py — no test asserts EXIF absence on a file written through the upload pipeline.

**Recommendation:** Add an integration test that calls save_photo with an EXIF-bearing JPEG, then verifies via exiftool/PIL that the persisted on-disk file has no EXIF metadata. Effort: small. Priority: recommended (mandatory fix for test coverage).

---

### MED-007: DEBUG-mode media serving bypasses nginx security headers

| Field | Value |
|-------|-------|
| **ID** | MED-007 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | apps/ads/views/listings.py (_serve_image, media_gate) |
| **Classification** | advisory |

**Description:** In production (DEBUG=False), media_gate returns an X-Accel-Redirect header and nginx applies Content-Security-Policy, X-Frame-Options: DENY, X-Content-Type-Options: nosniff, and MIME whitelisting (image/jpeg only) via the /protected-media/ location. But in DEBUG mode (DEBUG=True), _serve_image (listings.py:90-102) serves files via HttpResponse(data, content_type=image/jpeg) with none of the nginx security headers (no CSP, no X-Frame-Options, no nosniff, no Content-Disposition). This dev-mode path could be accidentally used in a staging environment with DEBUG=True, exposing images without the hardening the spec requires (db-schema.md:254-255: X-Content-Type-Options: nosniff, whitelists image/jpeg).

**Evidence:**
- listings.py:89-102 _serve_image — HttpResponse(data, content_type=image/jpeg), no security headers.
- listings.py:158-162 — DEBUG branch calls _serve_image directly.
- nginx.conf:74-84 /protected-media/ — has all headers; dev mode bypasses nginx entirely.

**Recommendation:** Add the same security headers (Content-Security-Policy, X-Frame-Options: DENY, X-Content-Type-Options: nosniff, Content-Disposition: inline) to the DEBUG-mode _serve_image response, so the dev path matches the production hardening. Effort: trivial. Priority: recommended.

---

### MED-008: AdImage.save() recomputes SHA-256 on every save where sha256 is blank

| Field | Value |
|-------|-------|
| **ID** | MED-008 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | apps/ads/models.py (AdImage.save, line 461-493), apps/media/services/hash_service.py (FileHashService) |
| **Classification** | advisory |

**Description:** AdImage.save() (models.py:461-493) computes SHA-256 on every call where self._state.adding or not self.sha256. The second condition means that any save of an existing AdImage with a blank sha256 recomputes the hash by reading the file from disk. In the normal bot flow, AdImage.objects.create() (line 725) fires save() once (creating with _state.adding=True), then ad_image.save() (line 746) is called again to persist the thumbnail keys — at this point _state.adding is False but sha256 is populated, so the recompute is skipped. However, edge cases (e.g. bulk_update, admin edits, or any code path that saves an existing AdImage with an empty sha256) would trigger an unnecessary full file read + SHA-256 computation. The backfill job (seed_service.py:271-288) correctly uses update() to bypass this, but the model-level logic is fragile: it should compute the hash only when the file field is first set, not on every save where sha256 happens to be blank.

**Evidence:**
- models.py:469 — if self._state.adding or not self.sha256: enters the hash-computation block on any save where sha256 is empty, regardless of whether the image field changed.
- models.py:477 — FileHashService.calculate_sha256(file_path) reads the entire file from disk.
- seed_service.py:288 — AdImage.objects.filter(pk=pk).update(sha256=file_hash) bypasses save() to avoid this; the model-level workaround is a code smell.

**Recommendation:** Compute SHA-256 only when the image field has changed (track via self._original_image or compare against the DB value); move the dedup check to fire only when _state.adding is True. Effort: small. Priority: recommended.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 1 |
| MEDIUM | 3 |
| LOW | 2 |
| **Total** | **7** |

## Mandatory Fixes

1. **MED-001 (CRITICAL):** Implement reference-counted AdImage.delete_files() helper that deletes image + all three thumbnail_* keys when the last referencing row is removed. Wire it into every sweep command (delete_sweep, purge_rejected_ads, purge_failed_ads, sweep_drafts, consent_hard_delete), soft_delete_user_ads, delete_draft, and an AdImage.pre_delete signal for ORM cascades. Required for both disk-hygiene (section 5d) and PII-erasure (section 5f, GDPR-equivalent) compliance.

2. **MED-002 (MEDIUM):** Detect duplicate upload before writing the file: compute SHA-256 at upload time and look up an existing AdImage by (user, sha256) prior to calling save_photo. If a match exists, reuse the existing key and discard the upload bytes. Alternatively, delete the just-written duplicate file inside AdImage.save() when dedup is detected.

3. **MED-003 (HIGH):** Enforce len(photos) >= 5 in process_photos before accepting a 6th photo; fix the misleading Please send at least 1 photo message to correctly state maximum 5 photos; clean up excess on-disk files when the count is rejected at done; add per-user/per-chat upload rate limiting in the bot or an nginx /media rate zone.

4. **MED-004 (MEDIUM):** Implement reference-counted physical deletion for shared keys (seed and dedup): before delete_photo(key), query AdImage.objects.filter(image=key).count() and only delete when count is 1 or less. Same for each thumbnail_* field.

5. **MED-006 (LOW):** Add an integration test verifying that an EXIF-bearing JPEG uploaded through save_photo produces a stripped on-disk file (via exiftool or PIL).

## Advisory Recommendations

1. **MED-005:** Add a periodic sweep_orphaned_media management command that diffs MEDIA_ROOT contents against all AdImage.image/thumbnail_* DB values and deletes unreferenced files. Run via cron alongside retention sweeps.

2. **MED-007:** Add Content-Security-Policy, X-Frame-Options: DENY, X-Content-Type-Options: nosniff, and Content-Disposition: inline headers to the DEBUG-mode _serve_image response so dev/staging matches production nginx hardening.

3. **MED-008:** Refactor AdImage.save() to compute SHA-256 only when the image field is newly set (detecting field change), not on every save where sha256 is blank. This prevents redundant full-file reads and removes the fragility that the seed backfill had to work around.

## Doc Updates Needed

1. **MED-001:** docs/01-spec/technical-specification.md:202 (photo dedup) and docs/02-database/db-schema.md:246-248 (thumbnail fields) should document that physical file deletion is reference-counted and includes thumbnail cleanup. Update the audit phase template section 5(d)/5(f) to reference the centralized AdImage.delete_files() contract.

2. **MED-002:** docs/01-spec/technical-specification.md:202 states dedup reuses existing storage — clarify that this means the file is not written at all (write-time lookup), not just the DB row.

3. **MED-003:** docs/01-spec/technical-specification.md:71 (1 to 5 photos) should specify that the count limit is enforced before disk write, not at the done checkpoint.

4. **MED-004:** docs/01-spec/technical-specification.md:144 and docs/02-database/db-schema.md:241-248 should document the reference-counting contract for shared storage keys (seed dedup).

5. **docs/02-database/db-schema.md:244** should note that ad_images.sha256 is computed on first save only (not re-computed on every save).

---

*Audit conducted against Phase 07 Media Handling and Security phase template.*
*Findings are advisory; mandatory classifications indicate spec deviations requiring immediate fix.*
