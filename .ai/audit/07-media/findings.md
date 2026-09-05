# Phase 07 Audit Findings — Media Handling & Security

**Executor:** audit-executor
**Template:** .kilo/commands/audit/phases/07-audit-media.md
**Status:** complete
**Validated:** no (static analysis only; Docker runtime not executed this phase)

## Findings

### ME-001: Path traversal in `delete_photo` — crafted `AdImage.image` escapes MEDIA_ROOT

| Field | Value |
|-------|-------|
| **ID** | ME-001 |
| **Severity** | CRITICAL |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/services/media.py, src/backend/apps/ads/models.py, src/backend/apps/core/management/commands/{delete_sweep,purge_rejected_ads,purge_failed_ads,purge_deleted_ads,sweep_drafts,consent_hard_delete}.py, src/backend/apps/ads/views/listings.py |
| **Classification** | mandatory |

**Description:** `delete_photo` builds the on-disk path with `os.path.join(settings.MEDIA_ROOT, storage_key)` (media.py:101) and unlinks it via `os.remove` (media.py:104) with no canonicalization and no containment check against MEDIA_ROOT. `storage_key` is sourced verbatim from the `AdImage.image` CharField, which declares only `max_length=64` and `help_text` — there is no `RegexValidator`, no `CheckConstraint`, and no `clean()` enforcing the documented `<uuid>.jpg` format. All six retention/PII sweep commands harvest `image` values with `values_list("image", flat=True)` and pass them straight to `delete_photo`. Any poisoned `AdImage.image` value containing `../`, a leading `/`, or an absolute path (possible via seed/import/admin writes or a future non-`generate_storage_key` writer) makes `os.remove` delete a file OUTSIDE MEDIA_ROOT. The serving path shares the root cause: `listings.py:109` `_serve_image` and `:186` X-Accel-Redirect both use the raw key, with only a DB-exists lookup as incidental defense. Phase 5(h) mandates crafted keys be rejected and keys contain only safe characters; the UUID-v4 contract (section 2) is unenforced at rest.

**Evidence:**
- src/telegram_bot/services/media.py:101 — `path = os.path.join(settings.MEDIA_ROOT, storage_key)`
- src/telegram_bot/services/media.py:104 — `os.remove(path)` (no realpath containment check)
- src/backend/apps/ads/models.py:525-528 — `image = models.CharField(max_length=64, help_text="Storage key (UUID v4 + .jpg ...")` — no validators, no constraint
- src/backend/apps/core/management/commands/delete_sweep.py:65-78 — `values_list("image", flat=True)` -> `delete_photo(storage_key)` verbatim (identical in purge_deleted_ads.py:66-79, purge_rejected_ads.py:65-79, purge_failed_ads.py:64-77, sweep_drafts.py:64-76, consent_hard_delete.py:69-90)
- src/backend/apps/ads/views/listings.py:109 — `_serve_image`: `file_path = settings.MEDIA_ROOT / image_key` (gated only by DB exists-check at listings.py:165)
- src/backend/apps/ads/tests/test_media_security.py:229-245 — only legit `seed/<filename>` subdir is tested; no test injects `../` or `..` into an AdImage.image row and exercises delete_photo or _serve_image

**Recommendation:** [BEST-PRACTICE] Add defense-in-depth at the media primitive: in `delete_photo` canonicalize with `os.path.realpath` and assert the result is within `os.path.realpath(MEDIA_ROOT)`; reject keys containing NUL, a leading `/`, or `..` components. Enforce the root cause with a `RegexValidator`/`CheckConstraint` on `AdImage.image` and `thumbnail_*` matching `^[A-Za-z0-9._-]+(\/[A-Za-z0-9._-]+)*\.jpg$` (allowing the documented `seed/<name>.jpg` namespace). Never rely on the DB lookup as the sole traversal barrier. effort: small; priority: recommended.

### ME-002: Sweep/erasure commands orphan thumbnail files — only `image` keys are collected

| Field | Value |
|-------|-------|
| **ID** | ME-002 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/services/media.py (delete_photo), src/backend/apps/ads/models.py (AdImage.thumbnail_*), src/backend/apps/core/management/commands/{delete_sweep,purge_deleted_ads,purge_rejected_ads,purge_failed_ads,sweep_drafts,consent_hard_delete}.py |
| **Classification** | mandatory |

**Description:** `ThumbnailService.generate_thumbnails` (thumbnails.py:73-77) stores three on-disk variants per photo keyed `<stem>-small.jpg` / `-medium.jpg` / `-large.jpg`, recorded in `AdImage.thumbnail_small/medium/large` (models.py:539-556). Every retention/PII sweep command, however, collects ONLY `AdImage.image` via `values_list("image", flat=True)` and calls `delete_photo` solely for those keys. The three thumbnail fields are never read or deleted. When an ARCHIVED/DELETED/REJECTED/FAILED/DRAFT ad or a consent-revoked user is purged, the main image rows cascade (DB-level) and the main image files are unlinked, but each surviving `AdImage` leaves three thumbnail files behind on disk — unbounded disk bloat and a direct violation of phase section 5(d) "no orphaned files" and section 7 ("Two ads reference the same file (dedup) -> sweep uses reference counting"). No code path anywhere calls `delete_photo` with a thumbnail key (grep across the repo confirms zero `delete_photo(.*thumbnail` references), so thumbnails are orphaned on every sweep and on PII erasure in particular.

**Evidence:**
- src/backend/apps/core/management/commands/delete_sweep.py:65-78 — `values_list("image", flat=True)` then `delete_photo(storage_key)`; thumbnails omitted (identical pattern in purge_deleted_ads.py:66-79, purge_rejected_ads.py:65-79, purge_failed_ads.py:64-77, sweep_drafts.py:64-76, consent_hard_delete.py:69-90)
- src/backend/apps/ads/models.py:539-556 — `thumbnail_small/medium/large` CharFields with no delete-side cleanup hook
- src/backend/apps/media/services/thumbnails.py:73-77 — thumbnails written as `<stem>-small.jpg` etc. alongside the main file
- grep `delete_photo(.*thumbnail` across all .py -> no matches (no thumbnail file is ever passed to delete_photo)
- src/backend/apps/ads/tests/test_media_security.py:313-344 — TestPhysicalDeletion only asserts delete_photo on main-image keys; no test asserts thumbnail cleanup

**Recommendation:** [SPEC-DEVIATION] Extend every sweep to collect all four physical keys per AdImage — `image`, `thumbnail_small`, `thumbnail_medium`, `thumbnail_large` (filtered to non-null) — in one `values_list` query and pass each to `delete_photo`. For deduplicated/shared seed thumbnails, gate deletion on a reference-count query (e.g. count AdImage rows referencing the key across all four columns) to honor the shared-file edge case. Add a regression test asserting thumbnail files are removed after a sweep. effort: medium; priority: recommended.

### ME-003: Non-atomic DB/delete + swallowed deletion failures with no reconciliation

| Field | Value |
|-------|-------|
| **ID** | ME-003 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/services/media.py (delete_photo:101-123), src/backend/apps/core/management/commands/{delete_sweep,purge_*,sweep_drafts,consent_hard_delete}.py, src/backend/apps/users/services/deletion.py |
| **Classification** | mandatory |

**Description:** Physical file removal runs OUTSIDE the DB transaction and AFTER `queryset.delete()` commits (delete_sweep.py:43-78; consent_hard_delete.py:45-90; identical in all six commands). This is an intentional trade-off (filesystem ops can't roll back), but it creates a two failure modes with no recovery path: (1) if the process crashes between the DB commit and the `delete_photo` loop exhausting `storage_keys`, DB rows are gone but files remain — silent orphans; (2) `delete_photo` exhausts its 3 retries for a transient `OSError` (media.py:110-123), then `logger.error(...)` and `return` — the failure is swallowed, no row is queued for retry, and the orphan persists invisibly. There is no dead-letter table, no re-schedule, and no periodic store-vs-DB reconciliation job (phase section 4.7 / 5(d) "FK cascade + file removal atomic" / section 5(e) idempotency). The advisory lock only makes a single run idempotent; it does not guarantee cross-run recovery of a crashed mid-loop or a persistently-locked file. Net effect: dangling rows->missing files and orphaned files->no rows, with no alerting.

**Evidence:**
- src/backend/apps/core/management/commands/delete_sweep.py:43-78 — `with transaction.atomic()` commits ORM delete (line 72) BEFORE the `for storage_key` loop calls `delete_photo` (line 77-78)
- src/telegram_bot/services/media.py:110-123 — `except OSError ... else: logger.error(...); return` swallows exhausted retries
- src/backend/apps/core/management/commands/consent_hard_delete.py:86-90 — same post-tx delete pattern for PII erasure
- src/backend/apps/users/services/deletion.py:96-159 — `hard_delete_user` documents "Filesystem deletions (delete_photo) are performed AFTER the transaction" but provides no retry/requeue
- grep for any "reconcile"/"dead_?letter"/"orphan" in src/backend/apps -> none found

**Recommendation:** [BEST-PRACTICE] After the committed delete, collect any `delete_photo` calls that exited via the error branch into an idempotent "pending_media_deletion" record (key + reason + attempt) for a background retry worker, OR run a periodic store-vs-DB reconciliation command that unlinks files with no matching AdImage row and logs rows whose file is missing. At minimum, escalate the exhausted-retry path from `logger.error` to a structured event/metric (not swallowed) so silent orphans are observable. effort: medium; priority: recommended.

### ME-004: No hard cap on mid-dialog photo uploads; >5 photo lands orphan files + misleading error

| Field | Value |
|-------|-------|
| **ID** | ME-004 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/handlers/ad_create.py (process_photos:646-720), src/telegram_bot/schemas/message_payloads.py (PhotoCountPayload:53-58), src/telegram_bot/services/media.py (validate_photo) |
| **Classification** | mandatory |

**Description:** The photo-upload handler `process_photos` (ad_create.py:646) has NO upper-bound guard before it downloads, validates, and `save_photo`s each incoming photo — `photos.append(...)` happens unconditionally (ad_create.py:708-714). The only "1-5" constraint is the `PhotoCountPayload(photo_count=count)` Pydantic check that fires on the "done" command AFTER the Nth photo is already written to disk (ad_create.py:657-665). Consequences: (1) a seller/bot can upload an unbounded number of photos (each ~2MB, fully EXIF-stripped via PIL) during the dialog, wasting disk and CPU — there is no per-upload count cap; (2) the 2MB-per-photo size cap is the only abuse limiter, and combined with ME-006 (no rate limit) this enables disk-exhaustion DoS; (3) when count > 5, "done" raises ValidationError and the user is answered "Please send at least 1 photo (you have N)" (ad_create.py:663) — the message is inverted (it says "at least 1" when the real problem is "more than 5"), and every photo beyond the 5th has already been saved to MEDIA_ROOT and is now orphaned because no AdImage row is ever created for it. Phase section 5(b) requires count 1-5 enforced; section 4.1 requires over-count rejected.

**Evidence:**
- src/telegram_bot/handlers/ad_create.py:646-720 — `process_photos` saves/validates each photo with no `if len(photos) >= 5: reject` guard; appends unconditionally at line 708
- src/telegram_bot/handlers/ad_create.py:656-665 — `PhotoCountPayload(photo_count=count)` (the only 1-5 enforcement) runs on "done", after disk write at line 704
- src/telegram_bot/handlers/ad_create.py:663 — misleading message "Please send at least 1 photo (you have 6)" on a >5 count
- src/telegram_bot/schemas/message_payloads.py:53-58 — `PhotoCountPayload.photo_count: Annotated[int, Field(ge=1, le=5, ...)]` exists but applies only at submission, not per-upload
- src/telegram_bot/services/media.py:30-73 — `validate_photo` enforces format/size/dimensions only, not cumulative count

**Recommendation:** [SPEC-DEVIATION] Enforce the hard cap at the upload edge: before `download_photo`/`validate_photo`, reject with a clear "5 photos maximum" message once `len(photos) >= 5`. Also fix the inverted error text. This prevents post-5 orphan files and the disk-abuse vector. effort: trivial; priority: recommended.

### ME-005: Decompression-bomb risk — full image decoded before dimension rejection

| Field | Value |
|-------|-------|
| **ID** | ME-005 |
| **Severity** | MEDIUM |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/services/media.py (validate_photo:30-73, strip_photo_exif:126-143) |
| **Classification** | advisory |

**Description:** `validate_photo` enforces the 2MB byte-size cap, then calls `Image.open(io.BytesIO(photo_bytes))` followed by `ImageOps.exif_transpose(img)` (media.py:59-61) BEFORE the dimension check at media.py:64. `exif_transpose` triggers a full pixel decode (`.load()`), so a JPEG whose compressed size is under 2MB but whose decompressed resolution is huge (e.g. a 10000x10000px "pixel-flood", ~300MB RGB) allocates the entire pixel buffer before Pillow reports `width > 2560` and rejects it. The project never sets `Image.MAX_IMAGE_PIXELS` (grep across src -> no matches), so it relies on Pillow's library default (~89M pixels): below 1x that is a silent `DecompressionBombWarning`, and only above 2x does it raise — a ~10000x10000 image (100M pixels) is below the 2x error threshold and is therefore fully decoded into ~300MB. Phase section 5(b) "bounded validation" and 5(g) "no worker crash or unbounded allocation on malicious input" / edge case "huge image -> rejected or bounded" are not satisfied. `strip_photo_exif` (media.py:139-143) re-decodes the same bytes on the write path, compounding the exposure.

**Evidence:**
- src/telegram_bot/services/media.py:54-55 — `if len(photo_bytes) > 2 * 1024 * 1024` size cap, checked before any decode
- src/telegram_bot/services/media.py:59-61 — `Image.open(...)` + `ImageOps.exif_transpose(img)` forces full decode
- src/telegram_bot/services/media.py:64 — dimension rejection happens AFTER the decode
- grep `MAX_IMAGE_PIXELS|DecompressionBomb` in src -> no matches (no project-level limit set)
- src/telegram_bot/services/media.py:139-143 — `strip_photo_exif` decodes again on the write path

**Recommendation:** [BEST-PRACTICE] Set `Image.MAX_IMAGE_PIXELS` project-wide (e.g. in the bot's app config / `apps.py` `ready()`) to a value just above the 2560x2560 ceiling (e.g. 2560*2560*2), and reject anything exceeding it as "Failed to process image" before full decode. Prefer `img.get_format_mimetype()`/metadata-only probe for the dimension check, or wrap decode in a try/except `DecompressionBombError`. effort: small; priority: recommended.

### ME-006: Upload rate limiter is defined but never invoked at the upload entry point

| Field | Value |
|-------|-------|
| **ID** | ME-006 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/services/rate_limit.py (check_upload_rate_limit:26-60), src/telegram_bot/handlers/ad_create.py (process_photos:646-720) |
| **Classification** | advisory |

**Description:** `check_upload_rate_limit` (rate_limit.py:26) implements an atomic `cache.add`/`cache.incr` sliding-window limiter keyed by `bot_upload_rl:{user_id}` (10 uploads / 60s) and is documented as the anti-burst control for photo uploads. It is NEVER imported or called: grep for `check_upload_rate_limit` returns only its own definition. The upload handler `process_photos` calls only `validate_photo` (ad_create.py:695) and `save_photo` (ad_create.py:704) — there is no rate check in between, so a seller (or a compromised bot client) can spam uploads unbounded in time, bounded only by Telegram's per-photo size limits. Combined with ME-004 (no hard count cap pre-submission), this leaves the upload path with no temporal bound at all, enabling disk/CPU exhaustion and queue saturation of the bot worker. Phase section 5(b) lists "rate limits enforced" as a HIGH check and section 4.1 requires "rapid spam -> rejected."

**Evidence:**
- src/telegram_bot/services/rate_limit.py:16-60 — `check_upload_rate_limit` defined with RATE_LIMIT_REQUESTS=10, RATE_LIMIT_PERIOD=60
- grep `check_upload_rate_limit` across all .py -> single match (only the definition)
- src/telegram_bot/handlers/ad_create.py:57-58 — imports `validate_photo, generate_storage_key, ...` but NOT `check_upload_rate_limit`
- src/telegram_bot/handlers/ad_create.py:646-720 — `process_photos` has no rate-limit call between download (686) and save (704)
- src/telegram_bot/services/__init__.py:3 — `__all__` exports only generate_storage_key/validate_photo/validate_jpeg_bytes; rate_limit is not re-exported, confirming it is dead to the upload flow

**Recommendation:** [SPEC-DEVIATION] Wire `check_upload_rate_limit(user_id)` (resolved from the FSM/session user) into `process_photos` before `download_photo`, returning HTTP/gram "uploading too fast, please wait" when it returns False. Add a unit test that calls it on a mocked cache and asserts the False path. effort: small; priority: recommended.

---

## Summary

| Severity | Count | IDs |
|----------|-------|-----|
| CRITICAL | 1 | ME-001 |
| HIGH | 4 | ME-002, ME-003, ME-004, ME-006 |
| MEDIUM | 1 | ME-005 |
| LOW | 0 | — |

## Mandatory Fixes (classification: mandatory)

1. **ME-001** CRITICAL — `delete_photo` path traversal: add `realpath` containment check and a `RegexValidator`/`CheckConstraint` on `AdImage.image`/`thumbnail_*` rejecting `../`, NUL, leading `/`, non-UUID-safe characters.
2. **ME-002** HIGH — orphan thumbnail files: sweeps must collect `thumbnail_small/medium/large` (non-null) alongside `image` and delete them, with reference-counting for shared seed keys.
3. **ME-003** HIGH — silent orphans on crash/swallowed retries: introduce a retry dead-letter or periodic store-vs-DB reconciliation; escalate exhausted-retry from `logger.error` to a metric.
4. **ME-004** HIGH — no upload count cap: reject at the upload edge once `len(photos) >= 5` before download/save; fix the inverted "at least 1 photo" message.

## Advisory Recommendations (classification: advisory)

1. **ME-005** MEDIUM — decompression-bomb: set `Image.MAX_IMAGE_PIXELS` project-wide; bound decode before dimension rejection.
2. **ME-006** HIGH — dead rate limiter: wire `check_upload_rate_limit(user_id)` into `process_photos` before `download_photo`; add a False-path unit test.

## Doc Updates Needed (type: DOC-UPDATE)

None — all findings map to code/logic gaps, not documentation drift.
