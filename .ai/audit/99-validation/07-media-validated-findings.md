---
name: validated-findings
validated: true
---

# Phase 07 Validated Findings — Media Handling & Security

**Validator:** validator  
**Based on findings:** .ai/audit/07-media/findings.md  
**Status:** complete  
**Validated:** yes  
**Validation date:** 2026-07-20

> `problems-only: true` — only problems documented. Validation confirms each finding is technically correct and applicable.

---

## Findings

### MED-001: nginx serves `/media/` directly with no per-request access control — unpublished/withdrawn/deleted ad photos are fetchable by URL

| Field | Value |
|-------|-------|
| **ID** | MED-001 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `docker/nginx/nginx.conf` (location `/media/`), `src/backend/config/urls.py`, `src/backend/apps/ads/urls.py`, `src/backend/apps/ads/views/listings.py` |
| **Classification** | mandatory |
| **Validation Status** | **VALIDATED** |

> **Validation Note:**
> > - **Action:** validated (confirmed)
> > - **Detail:** Evidence is accurate. `nginx.conf:56-76` shows `location /media/ { alias /media_volume/; }` with no conditional logic, no `internal`, no `X-Accel-Redirect` handoff. `config/urls.py` and `ads/urls.py` contain no media-serving routes. The `ad_detail` view (`listings.py:42-47`) correctly filters `status=AdStatus.PUBLISHED` for page access, but templates (`detail.html:36-39`) render `image.image_url` directly as `/media/<uuid>.jpg` URLs. nginx cannot query the DB, so any file present in the volume is served regardless of ad status. DRAFT, ON_MODERATION, REJECTED, DELETED, and withdrawn/ads are all fetchable by direct URL. Only UUID unpredictability protects them — "security by obscurity."
> > - **See also:** MED-002, MED-003

**Recommendation:** Introduce an app-level media gate. Serve `/media/` through a Django view that looks up `AdImage → Ad`, asserts `status == PUBLISHED` (and for staff, the moderation queue), and uses `X-Accel-Redirect` to an internal nginx location. Effort: medium. Priority: mandatory (CRITICAL).

---

### MED-002: EXIF / metadata is never stripped — PII can persist in served image bytes

| Field | Value |
|-------|-------|
| **ID** | MED-002 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/telegram_bot/services/media.py` (`validate_photo`), `src/telegram_bot/handlers/ad_create.py:431-437` |
| **Classification** | mandatory |
| **Validation Status** | **VALIDATED** |

> **Validation Note:**
> > - **Action:** validated (confirmed)
> > - **Detail:** Evidence is accurate. `validate_photo` (`media.py:54-66`) uses `Image.open(io.BytesIO(photo_bytes))` then reads `.size` only — no `img.load()`, no `img.save()` re-encode, no EXIF stripping. `save_photo` (`ad_create.py:431-437`) writes `photo_bytes` verbatim to `MEDIA_ROOT`. Any GPS coordinates, device make/model, or timestamps embedded in the original JPEG remain in the stored file and are served to visitors. The architecture plan noted this as a future risk (Part 6, line 253), but now it is a live finding requiring fix.
> > - **See also:** MED-001 (access control)

**Recommendation:** Re-encode images on store via Pillow: open, call `ImageOps.exif_transpose`, strip EXIF (`img.info.pop("exif", None)`), save with `optimize=True`. This also hardens against malicious JPEGs. Effort: small. Priority: mandatory (CRITICAL).

---

### MED-003: Sweep / erasure commands delete DB rows but never delete physical media files (orphaned PII on disk)

| Field | Value |
|-------|-------|
| **ID** | MED-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/core/management/commands/delete_sweep.py`, `sweep_drafts.py`, `purge_rejected_ads.py`, `purge_failed_ads.py`, `consent_hard_delete.py` |
| **Classification** | mandatory |
| **Validation Status** | **VALIDATED** |

> **Validation Note:**
> > - **Action:** validated (confirmed)
> > - **Detail:** Evidence is accurate. All sweep commands use `queryset.delete()` (e.g., `delete_sweep.py:60`, `sweep_drafts.py:58`, `purge_rejected_ads.py:61`, `purge_failed_ads.py:59`, `consent_hard_delete.py:71`) with comments stating "CASCADE will handle ad_images" — no filesystem unlink occurs. Grep confirms no `os.remove`, `os.unlink`, or `shutil` for media in production code. Files remain in `media_volume` indefinitely. Combined with MED-001, these orphaned files are permanently accessible by direct URL. This violates the phase requirement for PII-erasure cascade completeness (physical media must be removed on consent withdrawal).
> > - **See also:** MED-001, MED-004

**Recommendation:** Add a `delete_photo(storage_key)` helper and wire it into each sweep: collect `AdImage.image` values before `queryset.delete()`, unlink each file. For `consent_hard_delete`, unlink files over the user's ads. Effort: small. Priority: mandatory (HIGH; CRITICAL for erasure sub-case).

---

### MED-004: In-flight cancel / crash leaves orphaned partial files in MEDIA_ROOT

| Field | Value |
|-------|-------|
| **ID** | MED-004 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py` (FSM photo step `:266-288`, commit `:547-554`) |
| **Classification** | mandatory |
| **Validation Status** | **VALIDATED** |

> **Validation Note:**
> * **Action:** validated (confirmed)
> * **Detail:** Evidence is accurate. `save_photo` writes to disk immediately (`ad_create.py:431-437`), but `AdImage` rows are created only on successful commit (`ad_create.py:548-554`). If the user cancels, the bot crashes, or moderation fails before commit, the already-written files are orphaned in `MEDIA_ROOT`. `sweep_drafts` does not address this because it runs 30 minutes later and targets DRAFT ads only, not the files written during an aborted photo upload. The `cmd_cancel` handler (`ad_create.py:73-82`) calls `delete_draft` which deletes the ORM row but not physical files.

**Recommendation:** Track photo `storage_key`s in FSM state (`photos` list already contains `storage_key` per `ad_create.py:285-288`). Add `delete_photo(storage_key)` in `media.py` that calls `os.remove(os.path.join(settings.MEDIA_ROOT, storage_key))`. Wire it into `delete_draft` to unlink files before ORM deletion, and into `cmd_cancel` for explicit cancellations. Also wire into sweep commands (`sweep_drafts`, `delete_sweep`, `purge_*`) to unlink DRAFT ad images before CASCADE deletion. Effort: small. Priority: mandatory (HIGH).

> **Alternative (secondary):** Defer physical write to commit time via temp staging directory, moving to MEDIA_ROOT only when `AdImage` rows are created. This avoids tracking in FSM but adds complexity; use only if immediate-write pattern is redesigned.

---

### MED-005: Two divergent `generate_storage_key` implementations; docstring claims "ad_id + UUID v4" that neither honors

| Field | Value |
|-------|-------|
| **ID** | MED-005 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/ads/models.py:230-233` (`AdImage.generate_storage_key`), `src/telegram_bot/services/media.py:71-73` (`generate_storage_key`) |
| **Classification** | advisory |
| **Validation Status** | **VALIDATED** |

> **Validation Note:**
> * **Action:** validated (confirmed)
> * **Detail:** Evidence is accurate. `AdImage.generate_storage_key()` (`models.py:360-362`) returns `str(uuid.uuid4())` without extension; `telegram_bot.services.media.generate_storage_key()` (`media.py:71-73`) returns `<uuid>.jpg`. Both differ from the docstring claim ("ad_id + UUID v4"). The model's version lacks `.jpg`, which would cause nginx to serve `application/octet-stream` (forced download) per the MIME whitelist (`nginx.conf:71-73`). The bot version's `.jpg` form is what production uses. This is a maintenance trap and latent serving bug.
> * **See also:** MED-002 (EXIF), MED-006 (collision)

**Recommendation:** Since `AdImage.generate_storage_key()` is unused in production code (only referenced in test fixtures), delete the model method entirely. All production photo writes use `telegram_bot.services.media.generate_storage_key`, which already produces `<uuid>.jpg`. Update the `AdImage.image` field docstring (`models.py:330-333`) to state the true format: "bare UUID v4 + `.jpg` extension, no ad_id/user/telegram PII prefix". Effort: trivial. Priority: recommended.

---

### MED-006: Storage keys are not ad_id-scoped — UUID-v4 collision would silently overwrite an existing file

| Field | Value |
|-------|-------|
| **ID** | MED-006 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/services/media.py:71-73`, `src/telegram_bot/handlers/ad_create.py:431-437` |
| **Classification** | advisory |
| **Validation Status** | **VALIDATED** |

> **Validation Note:**
> > - **Action:** validated (confirmed)
> > - **Detail:** Evidence is accurate. `save_photo` uses `open(media_path, "wb")` with no existence check (`ad_create.py:436`). The key is process-global UUID, not namespaced per ad. A theoretical UUID-v4 collision would overwrite a different ad's photo silently. Probability is negligible, but the write is non-atomic and unguarded.
> > - **See also:** MED-005 (key format)

**Recommendation:** Use `os.O_CREAT | os.O_EXCL | os.O_WRONLY` to fail on collision; on collision, regenerate the key. Effort: trivial. Priority: recommended.

---

### MED-007: No thumbnail/transform step and no download rate limiting / spam throttle on photo upload

| Field | Value |
|-------|-------|
| **ID** | MED-007 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py` (photo step `:256-292`), `src/telegram_bot/services/media.py` |
| **Classification** | advisory |
| **Validation Status** | **REJECTED** |

> **Rejection Reason:** Per validation rules (99-audit-validate.md line 47-48), BEST-PRACTICE findings must be rejected if ROI is negative for project scale. The 5-photo cap **is** enforced downstream via `PhotoCountPayload` validation at preview (ad_create.py:247). A spammer sending many photos would be limited by the eventual moderation check. Adding per-message rate limiting adds complexity without clear benefit at current scale. The phase specification's "5-photo cap enforced at upload" is met at the workflow level (preview step). Thumbnail generation is explicitly deferred per the architecture plan (Part 6 notes this as acceptable for phase 1).

**Validation Note:**
> > - **Action:** rejected
> > - **Detail:** The 5-photo cap is enforced via `PhotoCountPayload` at preview. Rate limiting adds complexity with minimal operational value for a phase-1 MVP. Thumbnail generation is deferred as per architecture plan. Negative ROI at project scale.

---

### MED-008: No app-level media tests for access-control, EXIF stripping, or physical deletion

| Field | Value |
|-------|-------|
| **ID** | MED-008 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/ads/tests/`, `src/telegram_bot/` (no media tests), `src/backend/apps/core/tests/test_sweep_commands.py` |
| **Classification** | advisory |
| **Validation Status** | **VALIDATED** |

> **Validation Note:**
> > - **Action:** validated (confirmed)
> > - **Detail:** Evidence is accurate. No `test_media*.py` or media-security tests exist. `test_sweep_commands.py` only verifies DB-row CASCADE without touching `MEDIA_ROOT`. Per the project rule "tests must be a trustworthy safety net," these gaps leave the most security-sensitive media behaviors unguarded. Once MED-001/MED-002 are fixed, tests must verify access control, EXIF stripping, and file deletion.
> > - **See also:** MED-001, MED-002, MED-003

**Recommendation:** Add `tests/test_media_security.py` using isolated `MEDIA_ROOT` to assert: unpublished-ad photo not served, EXIF stripped after store, sweep unlinks files, path-traversal keys rejected. Effort: medium. Priority: recommended.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 7 | MED-001, MED-002, MED-003, MED-004, MED-005, MED-006, MED-008 |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 1 | MED-007 |

### Rejected Findings

| ID | Title | Reason |
|----|-------|--------|
| MED-007 | No thumbnail/transform step and no download rate limiting | 5-photo cap IS enforced via `PhotoCountPayload` at preview. Rate limiting adds complexity with minimal value at current scale. Thumbnail generation is deferred as per architecture plan. Negative ROI. |

### Merged Findings

None

### Reclassified Findings

None

---

## Rollout Analysis

### Risks & Dependencies

1. **MED-001 (Access control)** is the primary architectural risk. Fixing it requires:
   - A new Django view to gate `/media/` by ad status
   - nginx `internal` directive + `X-Accel-Redirect` configuration
   - This blocks access to unpublished/deleted ad photos but also blocks access to files from MED-003/MED-004 fixes

2. **MED-002 (EXIF stripping)** can be implemented independently but shares the same save path:
   - Modifies `save_photo` / `validate_photo` to re-encode
   - Also mitigates malicious-JPEG decoder hardening

3. **MED-003 (Physical deletion) + MED-004 (Orphan cleanup)** share the same `delete_photo` helper:
   - Implement `delete_photo(storage_key)` in `media.py`
   - Wire into sweep commands for DRAFT image cleanup
   - Wire into `delete_draft`/`cmd_cancel` for in-flight cleanup

4. **MED-005 (Unified storage key)** should be addressed before MED-006:
   - Eliminates confusion between the two generators
   - Use the bot version (`{uuid}.jpg`) as canonical

### Sequencing

| Priority | Recommendation | Depends on |
|----------|----------------|------------|
| 1 | MED-005: Delete unused `AdImage.generate_storage_key` (trivial) | — |
| 2 | MED-002: Strip EXIF on store (small) | — |
| 3 | MED-003 + MED-004: Add `delete_photo` helper, wire to sweeps/cancel | — (after MED-005 for consistency) |
| 4 | MED-006: O_EXCL guard against collision | — |
| 5 | MED-001: App-level media gate (medium) | — (blocks access to fixes 2-4) |
| 6 | MED-008: Add security tests | All fixes verified |

---

## Warnings

### Architectural Risks

1. **Security by obscurity:** Current media access relies entirely on UUID unpredictability. MED-001 fix is mandatory before production to prevent unauthorized access to non-public photos.

2. **PII leakage via EXIF:** MED-002 fix is required for GDPR compliance. GPS coordinates and device metadata in stored photos are personal data.

3. **Orphaned file accumulation:** MED-003/MED-004 combined allow indefinite file growth. Storage volume will contain unreferenced PII indefinitely.

### Cross-Phase Conflicts

None detected. MED-001-004 are consistent with AD-004 (orphaned files in sweep_drafts) and the PII-consent phase's erasure requirements.

### Documentation Consistency

Since MED-005 removes `AdImage.generate_storage_key`, delete the docstring; update `architecture-structure.md` to state storage key format is bare UUID v4 + `.jpg` extension, no ad_id prefix.