---
name: 07-media
phase: media
template: .ai/audit/templates/audit-findings.md
status: complete
validated: yes
validator: validator
validated_date: 2026-09-05
---

# Phase 07 Audit Findings — Media Handling & Security (Validated)

**Executor:** audit-executor
**Validator:** validator
**Template:** .ai/audit/templates/audit-findings.md
**Status:** complete
**Validated:** yes

**Scope:** Validation of Phase 07 media handling findings (ME-001 through ME-006) via grep + targeted source reads. Static-analysis-only validation — Docker runtime was NOT executed this phase (per original findings: "Validated: no"). All claims reproduced against actual source code.

This file is the self-contained validated report. The reader does not need to consult the original findings file (`.ai/audit/07-media/findings.md`).

---

## Runtime Verification Evidence

| Check | Result | Notes |
|-------|--------|-------|
| R1 — Import verification (WSGI) | N/A | Static analysis only; Docker runtime not executed |
| R1 — Import verification (bot) | N/A | Static analysis only; Docker runtime not executed |
| R3 — Linter (ruff) | N/A | Static analysis only |
| R3 — Type checker (basedpyright) | N/A | Static analysis only |
| Grep verification | PASS | All grep-based claims reproduced via ripgrep across `src/` and project root |
| Line-reference verification | PASS (with notes) | All cited source files read at exact line ranges; discrepancies noted per finding |
| Cross-reference check | PASS | Cross-referenced with Phase 03 (DB concurrency) findings for overlap; discovered `sweep_orphaned_media.py` and its broken enum reference |

---

## Cross-Finding Analysis

### Dependency Chains

| Finding | Depends on | Depends on by | Notes |
|---------|-----------|---------------|-------|
| ME-001 | — | ME-003 (shared function) | ME-001 adds containment check to `delete_photo`; ME-003 adds error escalation to the same function. Both modify `delete_photo` — should be in the same PR to avoid conflicts. |
| ME-002 | ME-001 (model validation) | — | If ME-001 adds a `RegexValidator`/`CheckConstraint` constraining `AdImage.image`/`thumbnail_*` to safe characters, the sweep extension for ME-002 becomes safer (traversal-proof keys guaranteed at rest). |
| ME-003 | — | ME-002 (shared backstop) | `sweep_orphaned_media.py` overlaps with both ME-002 (thumbnail orphan cleanup) and ME-003 (crash-recovery reconciliation). It is broken (see NEW-ME-007). |
| ME-004 | ME-006 (shared upload path) | — | ME-004 adds count cap; ME-006 wires in rate limiter. Both modify `process_photos` upload flow. Independent but composable. |
| ME-005 | — | ME-004 (shared validation) | ME-005 bounds decode size; ME-004 bounds count. Both strengthen `validate_photo`/`process_photos`. |
| ME-006 | — | ME-004 (shared upload path) | ME-006 wires `check_upload_rate_limit` into `process_photos`; ME-004 adds count cap to the same function. |

### Conflicts Detected

| Conflict | Description | Resolution |
|----------|-------------|------------|
| ME-003 vs. `sweep_orphaned_media.py` | ME-003 claims "there is no periodic store-vs-DB reconciliation job" and "grep for any reconcile/dead_?letter/orphan in src/backend/apps -> none found." Both claims are factually incorrect — `sweep_orphaned_media.py` exists at `src/backend/apps/media/management/commands/sweep_orphaned_media.py` and performs store-vs-DB reconciliation. However, the command is **broken** (`AdvisoryLockId.SWEEP_ORPHANED_MEDIA` is not defined in the enum) and **not scheduled** in the hourly scheduler, so no *working* reconciliation job exists. | Find the claim is substantively correct (no *working* reconciliation in practice) but the evidence is inaccurate. See NEW-ME-007 for the broken command. ME-003 remains VALIDATED with evidence quality caveat. |
| ME-003 vs. Phase 03 (DB-004) | Phase 03 DB-concurrency audit already identified the same non-atomic DB/delete pattern in `delete_sweep.py`, `sweep_drafts.py`, and `consent_hard_delete.py` (findings DB-004/DB-003). Its validated report (line 227) notes `delete_photo` already has 3-attempt retry and swallowed errors. ME-003 partially duplicates this finding. | Not a conflict — same root cause, different phase scope. Phase 03 focused on DB concurrency; Phase 07 focuses on media security. ME-003 adds media-specific concerns (swallowed errors as a silent-orphan problem). |

---

## Findings

### ME-001: Path traversal in `delete_photo` — crafted `AdImage.image` escapes MEDIA_ROOT

| Field | Value |
|-------|-------|
| **ID** | ME-001 |
| **Severity** | CRITICAL |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/services/media.py, src/backend/apps/ads/models.py, src/backend/apps/core/management/commands/{delete_sweep,purge_rejected_ads,purge_failed_ads,purge_deleted_ads,sweep_drafts,consent_hard_delete}.py, src/backend/apps/ads/views/listings.py |
| **Classification** | mandatory |
| **Validation Status** | **VALIDATED** |

**Description:** `delete_photo` builds the on-disk path with `os.path.join(settings.MEDIA_ROOT, storage_key)` (media.py:101) and unlinks it via `os.remove` (media.py:104) with no canonicalization and no containment check against MEDIA_ROOT. `storage_key` is sourced verbatim from the `AdImage.image` CharField, which declares only `max_length=64` and `help_text` — there is no `RegexValidator`, no `CheckConstraint`, and no `clean()` enforcing the documented `<uuid>.jpg` format. All six retention/PII sweep commands harvest `image` values with `values_list("image", flat=True)` and pass them straight to `delete_photo`. Any poisoned `AdImage.image` value containing `../`, a leading `/`, or an absolute path (possible via seed/import/admin writes or a future non-`generate_storage_key` writer) makes `os.remove` delete a file OUTSIDE MEDIA_ROOT. The serving path shares the root cause: `listings.py:109` `_serve_image` uses the raw key, with only a DB-exists lookup as incidental defense.

**Evidence:**
- src/telegram_bot/services/media.py:101 — `path = os.path.join(settings.MEDIA_ROOT, storage_key)`
- src/telegram_bot/services/media.py:104 — `os.remove(path)` (no realpath containment check)
- src/backend/apps/ads/models.py:525-528 — `image = models.CharField(max_length=64, help_text="Storage key (UUID v4 + .jpg ...")` — no validators, no constraint
- src/backend/apps/ads/models.py:565-567 — `class Meta` of `AdImage` has `db_table` and `ordering` only; NO `constraints` list
- src/backend/apps/ads/models.py:584 — `AdImage.save()` also builds `os.path.join(media_root, self.image)` with no containment check (additional traversal vector in the model's save path)
- src/backend/apps/core/management/commands/delete_sweep.py:65-78 — `values_list("image", flat=True)` -> `delete_photo(storage_key)` verbatim (identical in purge_deleted_ads.py:66-79, purge_rejected_ads.py:65-79, purge_failed_ads.py:64-77, sweep_drafts.py:64-76, consent_hard_delete.py:69-90)
- src/backend/apps/users/services/deletion.py:198-201 + 158-159 — `soft_delete_user_ads` also collects only `values_list("image", flat=True)` and passes to `delete_photo` (additional affected module not listed in the finding)
- src/backend/apps/ads/views/listings.py:109 — `_serve_image`: `file_path = settings.MEDIA_ROOT / image_key` (gated only by DB exists-check at listings.py:165)
- src/backend/apps/ads/views/listings.py:151 — `media_gate` has a control-char check (`any(ord(ch) < 0x20)`) that rejects NUL bytes but does NOT prevent `../` traversal
- src/backend/apps/ads/views/listings.py:186 — X-Accel-Redirect: `response["X-Accel-Redirect"] = f"/protected-media/{image_key}"` (raw key)
- src/backend/apps/ads/tests/test_media_security.py:229-245 — only legit `seed/kvartiry_01.jpg` subdir is tested; no test injects `../` or `..` into an `AdImage.image` row and exercises `delete_photo` or `_serve_image`
- src/backend/apps/ads/tests/test_media_security.py:313-348 — `TestPhysicalDeletion` only asserts `delete_photo` on main-image keys (`generate_storage_key()`); no test asserts traversal behavior

**Validator's Verification:**
- Read media.py:85-123 in full. Confirmed `path = os.path.join(settings.MEDIA_ROOT, storage_key)` at line 101, `os.remove(path)` at line 104, with no `os.path.realpath` containment check. The retry loop (lines 102-123) re-attempts the same path without canonicalization.
- Read models.py:525-528 (image field definition) and models.py:565-567 (AdImage Meta). Confirmed `image = models.CharField(max_length=64, help_text="Storage key (UUID v4 + .jpg, no ad_id/user/telegram PII")` with zero `validators=`, zero `RegexValidator`. The `class Meta` has only `db_table = "ad_images"` and `ordering = ["position"]` — no `constraints` list. The 6 `CheckConstraint` instances at models.py:318-339 belong to the `Ad` model, not `AdImage`.
- Read models.py:572-591 (AdImage.save). Confirmed `file_path = os.path.join(media_root, self.image)` at line 584 — the same traversal vector exists in the model's save path. No `clean()` method is defined on `AdImage` (the class has fields, Meta, __str__, save, image_url, thumbnail_small_url — no clean).
- Read all six sweep command files (delete_sweep.py, purge_deleted_ads.py, purge_rejected_ads.py, purge_failed_ads.py, sweep_drafts.py, consent_hard_delete.py). Confirmed each collects `AdImage.objects.filter(ad_id__in=ad_ids).values_list("image", flat=True)` and passes keys verbatim to `delete_photo(storage_key)`. Verified all exact line numbers cited in the evidence.
- Read deletion.py:189-205 (soft_delete_user_ads). Confirmed it also collects only `values_list("image", flat=True)` at line 198-201 and passes to `delete_photo` at line 158-159. This is an additional affected module not listed in the finding's "Affected Modules."
- Read listings.py:102-187 in full. Confirmed `_serve_image` at line 109 does `file_path = settings.MEDIA_ROOT / image_key` with no containment check. Confirmed `media_gate` has a control-char check at line 151 (`if any(ord(ch) < 0x20 for ch in image_key): raise Http404`) — this rejects NUL bytes but does NOT prevent `../` or absolute-path traversal, since `.` and `/` have no control characters. The DB exists-check at line 165 is the only defense before `_serve_image` is called, and it provides NO traversal protection if a poisoned `AdImage.image` row exists in the DB.
- Read test_media_security.py in full (543 lines). Confirmed `test_seed_storage_key_with_path_returns_redirect` (lines 229-245) only tests the legit `seed/kvartiry_01.jpg` key. `TestPathTraversalRejection` (lines 350-392) tests URL-level traversal (`/media/../../../etc/passwd`) against the `media_gate` view — these tests rely on the DB-lookup returning no matches (404), NOT on a containment check in `delete_photo`. No test injects a `../` key into an `AdImage.image` row and then calls `delete_photo` on it.
- Grep `from telegram_bot.services.media import delete_photo` across `src/backend/`: confirmed all 7 production import sites (delete_sweep, purge_deleted_ads, purge_rejected_ads, purge_failed_ads, sweep_drafts, consent_hard_delete, deletion.py).
- Grep `RegexValidator` across `src/backend/apps/ads/models.py`: 0 matches (no validators on any AdImage field).

**Evidence Quality:** **High** — all code claims verified at exact line numbers. Minor gap: the finding cites "seven backend modules" in the Phase 01 validated report's ENT-001 for `delete_photo` imports, but ME-001 itself only names the 6 management commands; the 7th (`users/services/deletion.py`) was not listed in ME-001's affected modules but is confirmed to also call `delete_photo`.

**Recommendation:** [BEST-PRACTICE] Add defense-in-depth at the media primitive: in `delete_photo`, canonicalize with `os.path.realpath` and assert the result is within `os.path.realpath(MEDIA_ROOT)`; reject keys containing NUL, a leading `/`, or `..` components. Enforce the root cause with a `RegexValidator`/`CheckConstraint` on `AdImage.image` and `thumbnail_*` matching `^[A-Za-z0-9._-]+(\/[A-Za-z0-9._-]+)*\.jpg$` (allowing the documented `seed/<name>.jpg` namespace). Never rely on the DB lookup as the sole traversal barrier.

> **Validation Note:**
> - **Action:** reclassified (evidence addition)
> - **Detail:** An additional traversal vector was discovered in `AdImage.save()` at models.py:584 (`os.path.join(media_root, self.image)`) — the same unvalidated `image` field is used to build a filesystem path for SHA-256 computation with no containment check. This is a manifestation of the same root cause (no validation on the `image` field) and should be addressed alongside the `delete_photo` fix.
> - **See also:** ME-002 (same unvalidated-field root cause for thumbnails), ME-007 (broken orphan sweep)

---

### ME-002: Sweep/erasure commands orphan thumbnail files — only `image` keys are collected

| Field | Value |
|-------|-------|
| **ID** | ME-002 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/services/media.py (delete_photo), src/backend/apps/ads/models.py (AdImage.thumbnail_*), src/backend/apps/core/management/commands/{delete_sweep,purge_deleted_ads,purge_rejected_ads,purge_failed_ads,sweep_drafts,consent_hard_delete}.py |
| **Classification** | mandatory |
| **Validation Status** | **VALIDATED** |

**Description:** `ThumbnailService.generate_thumbnails` (thumbnails.py:74-77) stores three on-disk variants per photo keyed `<stem>-small.jpg` / `-medium.jpg` / `-large.jpg`, recorded in `AdImage.thumbnail_small/medium/large` (models.py:539-556). Every retention/PII sweep command, however, collects ONLY `AdImage.image` via `values_list("image", flat=True)` and calls `delete_photo` solely for those keys. The three thumbnail fields are never read or deleted. When an ARCHIVED/DELETED/REJECTED/FAILED/DRAFT ad or a consent-revoked user is purged, the main image rows cascade (DB-level) and the main image files are unlinked, but each surviving `AdImage` leaves three thumbnail files behind on disk.

**Evidence:**
- src/backend/apps/core/management/commands/delete_sweep.py:65-78 — `values_list("image", flat=True)` then `delete_photo(storage_key)`; thumbnails omitted (identical pattern in purge_deleted_ads.py:66-79, purge_rejected_ads.py:65-79, purge_failed_ads.py:64-77, sweep_drafts.py:64-76, consent_hard_delete.py:69-90)
- src/backend/apps/ads/models.py:539-556 — `thumbnail_small/medium/large` CharFields with no delete-side cleanup hook
- src/backend/apps/media/services/thumbnails.py:74-75 — `key = f"{stem}-{size_enum.value}.jpg"` generates `<stem>-{small|medium|large}.jpg` variants (confirmed enum values at enums.py:86-91: SMALL="small", MEDIUM="medium", LARGE="large")
- src/backend/apps/ads/models.py:539-556 + ad_create.py:1212-1221 — thumbnail keys ARE persisted to model fields (AdImageService.create_or_skip stores them)
- grep `delete_photo(.*thumbnail` across all .py -> no matches (no thumbnail file is ever passed to delete_photo)
- src/backend/apps/ads/tests/test_media_security.py:313-348 — TestPhysicalDeletion only asserts delete_photo on main-image keys; no test asserts thumbnail cleanup
- src/backend/apps/media/tests/test_save_photo_integration.py:114-116 — confirms thumbnails ARE stored in model fields (asserting `ad_image.thumbnail_small == "photo-small.jpg"`, etc.)

**Validator's Verification:**
- Read thumbnails.py:40-100 in full. Confirmed `generate_thumbnails` returns a `dict[ThumbnailSizeStrEnum, str]` where each key is `f"{stem}-{size_enum.value}.jpg"` (line 75). Read enums.py:86-91: `ThumbnailSizeStrEnum` with SMALL="small", MEDIUM="medium", LARGE="large".
- Read models.py:539-556: confirmed `thumbnail_small`, `thumbnail_medium`, `thumbnail_large` are `CharField(max_length=64, blank=True, null=True, help_text=...)`.
- Read models.py:565-567: AdImage Meta has no signals, no `pre_delete`/`post_delete` hooks. No `delete()` override on AdImage. No `clean()` method. Thumbnails are NOT cleaned up on model instance deletion.
- Read all six sweep command files: confirmed each uses `values_list("image", flat=True)` and iterates only those keys through `delete_photo`. None reference `thumbnail_small`, `thumbnail_medium`, or `thumbnail_large`.
- Confirmed thumbnail keys ARE persisted to model fields: read ad_create.py:1212-1221 (AdImageService.create_or_skip stores thumbnail keys), seed generators/images.py:181-183 (seed stores thumbnail keys), copy_service.py:65-67 (copy preserves thumbnail keys), and test_save_photo_integration.py:114-116 (test asserts thumbnails stored).
- Grep `delete_photo\(.*thumbnail` across all .py in `src/`: 0 matches. Confirmed the finding's claim.
- Read test_media_security.py:313-348 (TestPhysicalDeletion): confirmed it only tests `delete_photo(key)` where `key = generate_storage_key()` (a main-image UUID key). The `TestMediaGateThumbnailResolution` class (lines 395-543) tests thumbnail *resolution* in `media_gate` (serving) but NOT thumbnail *deletion* in sweeps.
- **Mitigating backstop discovered:** `sweep_orphaned_media.py` exists at `src/backend/apps/media/management/commands/sweep_orphaned_media.py` (132 lines). It walks MEDIA_ROOT (excluding `seed/`), collects all 4 AdImage fields (`image`, `thumbnail_small`, `thumbnail_medium`, `thumbnail_large`) as referenced keys (line 36-41), and deletes unreferenced files via `os.remove` (lines 109-121). This is a store-vs-DB reconciliation that would eventually reclaim orphaned thumbnails. **However**, this command is **broken** — it references `AdvisoryLockId.SWEEP_ORPHANED_MEDIA` (line 87) which does NOT exist in the `AdvisoryLockId` enum (enums.py:23-42). It is also **not scheduled** in the hourly scheduler (`docker/entrypoint-scheduler.sh` lines 28-37 list 8 commands, none is `sweep_orphaned_media`) and has **no tests**. See NEW-ME-007.

**Evidence Quality:** **High** — all core technical claims verified at exact line numbers. The finding did not mention the `sweep_orphaned_media.py` backstop; while its existence partially mitigates the "unbounded disk bloat" framing, the command is non-functional (broken enum reference) and unscheduled, so thumbnails are truly orphaned in practice.

**Recommendation:** [SPEC-DEVIATION] Extend every sweep to collect all four physical keys per AdImage — `image`, `thumbnail_small`, `thumbnail_medium`, `thumbnail_large` (filtered to non-null) — in one `values_list` query and pass each to `delete_photo`. For deduplicated/shared seed thumbnails, gate deletion on a reference-count query. Add a regression test asserting thumbnail files are removed after a sweep. Also fix `sweep_orphaned_media.py` (NEW-ME-007) to make the reconciliation backstop functional and schedule it.

> **Validation Note:**
> - **Action:** evidence addition
> - **Detail:** A `sweep_orphaned_media.py` reconciliation command exists but is broken (references non-existent `AdvisoryLockId.SWEEP_ORPHANED_MEDIA`) and unscheduled. This means the orphan sweep does NOT currently function as a backstop — thumbnail orphans accumulate with no automated reclamation. The finding's core claim (sweeps don't delete thumbnail files) is correct; the "unbounded disk bloat" framing is accurate in practice because the backstop is non-functional.
> - **See also:** NEW-ME-007 (broken orphan sweep), ME-001 (shared root cause: unvalidated image field)

---

### ME-003: Non-atomic DB/delete + swallowed deletion failures with no reconciliation

| Field | Value |
|-------|-------|
| **ID** | ME-003 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/services/media.py (delete_photo:85-123), src/backend/apps/core/management/commands/{delete_sweep,purge_*,sweep_drafts,consent_hard_delete}.py, src/backend/apps/users/services/deletion.py |
| **Classification** | mandatory |
| **Validation Status** | **VALIDATED** |

**Description:** Physical file removal runs OUTSIDE the DB transaction and AFTER `queryset.delete()` commits (delete_sweep.py:43-78; consent_hard_delete.py:45-90; identical in all six commands). This is an intentional trade-off (filesystem ops can't roll back), but it creates two failure modes with no recovery path: (1) if the process crashes between the DB commit and the `delete_photo` loop exhausting `storage_keys`, DB rows are gone but files remain — silent orphans; (2) `delete_photo` exhausts its 3 retries for a transient `OSError` (media.py:110-123), then `logger.error(...)` and `return` — the failure is swallowed, no row is queued for retry, and the orphan persists invisibly.

**Evidence:**
- src/backend/apps/core/management/commands/delete_sweep.py:43-78 — `with transaction.atomic()` commits ORM delete (line 72) BEFORE the `for storage_key` loop calls `delete_photo` (line 77-78)
- src/telegram_bot/services/media.py:110-123 — `except OSError ... else: logger.error(...); return` swallows exhausted retries
- src/backend/apps/core/management/commands/consent_hard_delete.py:45-90 — same post-tx delete pattern (tx at 45, ORM delete at 84, delete_photo loop at 89-90)
- src/backend/apps/users/services/deletion.py:155-159 — `withdraw_consent` performs `delete_photo` after `transaction.atomic()` exits; docstring (lines 94-98) documents "Filesystem deletions (delete_photo) are performed AFTER the transaction"
- src/backend/apps/users/services/deletion.py:189-205 — `soft_delete_user_ads` also collects only `values_list("image", flat=True)` (line 198-201)

**Validator's Verification:**
- Read delete_sweep.py:39-85 in full. Confirmed `with transaction.atomic():` at line 43 wraps the queryset filter and `queryset.delete()` at line 72. The `for storage_key in storage_keys: delete_photo(storage_key)` loop (lines 77-78) is at function-body indentation — OUTSIDE the `with transaction.atomic():` block.
- Read consent_hard_delete.py:41-97 in full. Confirmed identical pattern: `with transaction.atomic():` at line 45, `queryset.delete()` at line 84, `for storage_key in storage_keys: delete_photo(storage_key)` at lines 89-90 (outside the tx).
- Read purge_deleted_ads.py, purge_rejected_ads.py, purge_failed_ads.py, sweep_drafts.py: confirmed all follow the identical pattern (tx wraps `values_list` + `delete()`; `delete_photo` loop is outside).
- Read media.py:102-123 (delete_photo body). Confirmed the retry loop: `for attempt in range(DELETE_PHOTO_MAX_ATTEMPTS):` with `try: os.remove(path)` at line 104. On `OSError` after all retries, line 119 `logger.error(...)` and line 123 `return` — the error is logged but swallowed (no exception raised, no retry record queued).
- Read deletion.py:75-162 (withdraw_consent) and 165-221 (soft_delete_user_ads). Confirmed `withdraw_consent` calls `delete_photo` at lines 158-159 (after `transaction.atomic()` exits at line 116). The docstring at lines 94-98 documents the TX-then-Filesystem pattern. **`soft_delete_user_ads` collects only `values_list("image", flat=True)` at line 198-201** — thumbnails are not collected here either (consistent with ME-002).

**Evidence Quality Issues (corrected):**
- The finding cites "deletion.py:96-159" and calls the function `hard_delete_user`. The actual function is **`withdraw_consent`** (lines 75-162), not `hard_delete_user`. There is no `hard_delete_user` function in deletion.py. The line range 96-159 falls within `withdraw_consent`'s body and covers the relevant docstring + post-tx delete loop. The substance is correct; the function name is wrong.
- The finding claims "There is no dead-letter table, no re-schedule, and no periodic store-vs-DB reconciliation job (phase section 4.7 / 5(d) 'FK cascade + file removal atomic' / section 5(e) idempotency)." **This claim is inaccurate.** A store-vs-DB reconciliation command — `sweep_orphaned_media.py` — DOES exist at `src/backend/apps/media/management/commands/sweep_orphaned_media.py` (132 lines). It walks MEDIA_ROOT, collects referenced keys across all 4 AdImage fields, and deletes unreferenced files via `os.remove`. **However**, this command is **broken** — it references `AdvisoryLockId.SWEEP_ORPHANED_MEDIA` (line 87) which is NOT defined in `AdvisoryLockId` (enums.py:23-42), causing `AttributeError` at runtime. It is also **not scheduled** in the hourly scheduler (entrypoint-scheduler.sh:28-37 lists 8 commands; `sweep_orphaned_media` is absent) and has **no tests**.
- The finding claims "grep for any 'reconcile'/'dead_?letter'/'orphan' in src/backend/apps -> none found." **This grep claim is false.** A grep for `reconcile|dead_?letter|orphan|pending_media` in `src/backend/apps` returns 35 matches, including `sweep_orphaned_media.py` (which contains "orphan" in its docstring, comments, and code at lines 2, 29, 63, 91, 96, 98, 102, 109, 121, 130), `_reconcile_preferred_city_on_login` in `users/views/consent.py:322`, and "orphan" in comments in `deletion.py:157,171,192`, `seed_service.py:229,245`, and `test_deletion.py:327,340`. The finding's grep may have used a different scope or pattern.

**Evidence Quality:** **Medium-High** — The core technical claims (non-atomic DB/delete, swallowed errors) are verified at exact line numbers in all six sweep commands + deletion.py. However, the finding's evidence contains two factually incorrect claims: (1) "no periodic store-vs-DB reconciliation job" — `sweep_orphaned_media.py` exists but is broken and unscheduled; (2) the grep claim for "orphan" matches is false. The substance (no *working* reconciliation) is correct, but the evidence statements are inaccurate.

**Recommendation:** [BEST-PRACTICE] After the committed delete, collect any `delete_photo` calls that exited via the error branch into an idempotent "pending_media_deletion" record (key + reason + attempt) for a background retry worker, OR run a periodic store-vs-DB reconciliation command that unlinks files with no matching AdImage row and logs rows whose file is missing. At minimum, escalate the exhausted-retry path from `logger.error` to a structured event/metric (not swallowed) so silent orphans are observable. **Critically:** fix `sweep_orphaned_media.py` (NEW-ME-007) to make the existing reconciliation command functional and schedule it in the hourly scheduler.

> **Validation Note:**
> - **Action:** evidence correction
> - **Detail:** The finding's evidence contains two inaccurate claims: (1) "there is no periodic store-vs-DB reconciliation job" is false — `sweep_orphaned_media.py` exists; (2) the grep claim "grep for any reconcile/dead_?letter/orphan in src/backend/apps -> none found" is false (35 matches found). The SUBSTANCE is correct because the orphan sweep is broken (non-existent enum member `AdvisoryLockId.SWEEP_ORPHANED_MEDIA`) and unscheduled, so no working reconciliation exists. The core non-atomicity and swallowed-error claims remain validated.
> - **See also:** NEW-ME-007 (broken orphan sweep command), ME-002 (shared orphan problem)

---

### ME-004: No hard cap on mid-dialog photo uploads; >5 photo lands orphan files + misleading error

| Field | Value |
|-------|-------|
| **ID** | ME-004 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/handlers/ad_create.py (process_photos:646-720), src/telegram_bot/schemas/message_payloads.py (PhotoCountPayload:53-58), src/telegram_bot/services/media.py (validate_photo) |
| **Classification** | mandatory |
| **Validation Status** | **VALIDATED** |

**Description:** The photo-upload handler `process_photos` (ad_create.py:646) has NO upper-bound guard before it downloads, validates, and `save_photo`s each incoming photo — `photos.append(...)` happens unconditionally (ad_create.py:708-714). The only "1-5" constraint is the `PhotoCountPayload(photo_count=count)` Pydantic check that fires on the "done" command AFTER the Nth photo is already written to disk (ad_create.py:660). Consequences: (1) a seller/bot can upload an unbounded number of photos (each ~2MB, fully EXIF-stripped via PIL) during the dialog, wasting disk and CPU — there is no per-upload count cap; (2) when count > 5, "done" raises ValidationError and the user is answered "Please send at least 1 photo (you have N)" (ad_create.py:663) — the message is inverted (it says "at least 1" when the real problem is "more than 5"), and every photo beyond the 5th has already been saved to MEDIA_ROOT and is now orphaned because no AdImage row is ever created for it.

**Evidence:**
- src/telegram_bot/handlers/ad_create.py:646-720 — `process_photos` saves/validates each photo with no `if len(photos) >= 5: reject` guard; appends unconditionally at line 708
- src/telegram_bot/handlers/ad_create.py:656-665 — `PhotoCountPayload(photo_count=count)` (the only 1-5 enforcement) runs on "done", after disk write at line 704
- src/telegram_bot/handlers/ad_create.py:663 — misleading message "Please send at least 1 photo (you have {count})" on a >5 count
- src/telegram_bot/schemas/message_payloads.py:53-58 — `PhotoCountPayload.photo_count: Annotated[int, Field(ge=1, le=5, ...)]` exists but applies only at submission, not per-upload
- src/telegram_bot/services/media.py:30-73 — `validate_photo` enforces format/size/dimensions only, not cumulative count

**Validator's Verification:**
- Read ad_create.py:646-720 in full (process_photos). Confirmed the flow:
  1. Line 656: `if message.text and message.text.strip().lower() == "done":` — detects "done" command
  2. Line 660: `PhotoCountPayload(photo_count=count)` — validates count AFTER all photos are already saved to disk
  3. Line 663: `await message.answer(f"Please send at least 1 photo (you have {count}).")` — misleading message (says "at least 1" when the issue is >5)
  4. Lines 675-700: validate photo exists, get largest, download (line 686), validate (line 695)
  5. Line 704: `save_photo(...)` — writes to disk
  6. Lines 708-714: `photos.append(...)` — added to state unconditionally, NO count check
  7. Line 719: responds with `f"Photo saved ({len(photos)}/5)..."` — shows count progress but never rejects >5
- Confirmed there is NO `if len(photos) >= 5:` or equivalent guard anywhere in the photo-processing path before download/save.
- Read message_payloads.py:53-58: confirmed `PhotoCountPayload` with `photo_count: Annotated[int, Field(ge=1, le=5, ...)]`. The `ge=1` lower bound means this validator would also accept `count=0` on the "done" path and reject with ValidationError — consistent with the misleading message.
- Read media.py:30-73 (validate_photo): confirmed it checks magic bytes, size (2MB), dimensions (2560px), but has NO count parameter.
- Read save_photo (ad_create.py:961-1008+): confirmed it strips EXIF via `strip_photo_exif` and writes to disk via `os.open` with `O_CREAT|O_EXCL` — no count awareness.
- Confirmed ad_create.py imports (`from telegram_bot.services.media import generate_storage_key, validate_photo, strip_photo_exif, delete_photo` at lines 56-61): `check_upload_rate_limit` from `telegram_bot.services.rate_limit` is NOT imported (see ME-006).

**Evidence Quality:** **High** — all claims verified at exact line numbers.

**Recommendation:** [SPEC-DEVIATION] Enforce the hard cap at the upload edge: before `download_photo`/`validate_photo`, reject with a clear "5 photos maximum" message once `len(photos) >= 5`. Also fix the inverted error text. This prevents post-5 orphan files and the disk-abuse vector.

> **Validation Note:**
> - **Action:** none (validated as-is)
> - **Detail:** No corrections needed. All line references and claims verified exact. The flow is: "done" → PhotoCountPayload check (post-write) → misleading message; regular photo → download → validate → save → append (no cap). The cap must be enforced before the append, not at "done".

---

### ME-005: Decompression-bomb risk — full image decoded before dimension rejection

| Field | Value |
|-------|-------|
| **ID** | ME-005 |
| **Severity** | MEDIUM |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/services/media.py (validate_photo:30-73, strip_photo_exif:126-143) |
| **Classification** | advisory |
| **Validation Status** | **VALIDATED** |

**Description:** `validate_photo` enforces the 2MB byte-size cap, then calls `Image.open(io.BytesIO(photo_bytes))` followed by `ImageOps.exif_transpose(img)` (media.py:59-61) BEFORE the dimension check at media.py:64. `exif_transpose` triggers a full pixel decode (`.load()`), so a JPEG whose compressed size is under 2MB but whose decompressed resolution is huge (e.g. a 10000x10000px "pixel-flood", ~300MB RGB) allocates the entire pixel buffer before Pillow reports `width > 2560` and rejects it. The project never sets `Image.MAX_IMAGE_PIXELS`, so it relies on Pillow's library default (~89M pixels): below 1x that is a silent `DecompressionBombWarning`, and only above 2x does it raise — a ~10000x10000 image (100M pixels) is below the 2x error threshold and is therefore fully decoded into ~300MB. `strip_photo_exif` (media.py:139-143) re-decodes the same bytes on the write path, compounding the exposure.

**Evidence:**
- src/telegram_bot/services/media.py:54-55 — `if len(photo_bytes) > 2 * 1024 * 1024` size cap, checked before any decode
- src/telegram_bot/services/media.py:59-61 — `Image.open(io.BytesIO(photo_bytes))` + `ImageOps.exif_transpose(img)` forces full decode
- src/telegram_bot/services/media.py:64 — dimension rejection happens AFTER the decode
- grep `MAX_IMAGE_PIXELS|DecompressionBomb` in src -> no matches (no project-level limit set)
- src/telegram_bot/services/media.py:139-143 — `strip_photo_exif` decodes again on the write path

**Validator's Verification:**
- Read media.py:30-73 (validate_photo). Confirmed the order: magic-byte check (line 50) → 2MB size cap (line 54) → `Image.open` + `ImageOps.exif_transpose` (lines 59-61) → dimension check (line 64). The decode at line 59-61 occurs BEFORE the dimension check at line 64, meaning a huge-resolution-but-under-2MB image is fully decoded into memory before the dimension guard rejects it.
- Confirmed `ImageOps.exif_transpose(img)` at line 61 triggers a full `.load()` of pixel data. Pillow's `exif_transpose` internally accesses pixel data to produce the transposed image.
- Grep `MAX_IMAGE_PIXELS` across entire `src/` directory: **0 matches**.
- Grep `PILLOW_MAX_IMAGE_PIXELS` across entire project root: **0 matches** (no environment variable configuration).
- Read media.py:126-143 (strip_photo_exif): confirmed it calls `Image.open(io.BytesIO(photo_bytes))` at line 139 and `ImageOps.exif_transpose(img)` at line 140 — a SECOND full decode of the same bytes on the write path (called from `save_photo` at ad_create.py:980).
- Confirmed Pillow's default `MAX_IMAGE_PIXELS` behavior: at ~89M pixels (1x threshold) a `DecompressionBombWarning` is emitted (not an error); at ~178M pixels (2x threshold) a `DecompressionBombError` is raised. A 10000x10000 image (100M pixels) is below the 2x threshold (~89M × 2 = 178M) and above the silent 1x threshold, so it is fully decoded with only a warning.

**Evidence Quality:** **High** — all claims verified at exact line numbers and against Pillow's documented behavior.

**Recommendation:** [BEST-PRACTICE] Set `Image.MAX_IMAGE_PIXELS` project-wide (e.g. in the bot's app config / `ready()`) to a value just above the 2560x2560 ceiling (e.g. 2560*2560*2), and reject anything exceeding it as "Failed to process image" before full decode. Prefer metadata-only probe for the dimension check, or wrap decode in try/except `DecompressionBombError`.

> **Validation Note:**
> - **Action:** none (validated as-is)
> - **Detail:** All claims verified exact. The only inaccuracy in the evidence is the phrase "no project-level limit set" — more precisely, the limit is not set anywhere in source code or environment configuration. Pillow's default applies.

---

### ME-006: Upload rate limiter is defined but never invoked at the upload entry point

| Field | Value |
|-------|-------|
| **ID** | ME-006 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/telegram_bot/services/rate_limit.py (check_upload_rate_limit:26-60), src/telegram_bot/handlers/ad_create.py (process_photos:646-720) |
| **Classification** | advisory |
| **Validation Status** | **VALIDATED** |

**Description:** `check_upload_rate_limit` (rate_limit.py:26) implements an atomic `cache.add`/`cache.incr` sliding-window limiter keyed by `bot_upload_rl:{user_id}` (10 uploads / 60s) and is documented as the anti-burst control for photo uploads. It is NEVER imported or called: grep for `check_upload_rate_limit` returns only its own definition. The upload handler `process_photos` calls only `validate_photo` (ad_create.py:695) and `save_photo` (ad_create.py:704) — there is no rate check in between, so a seller (or a compromised bot client) can spam uploads unbounded in time, bounded only by Telegram's per-photo size limits.

**Evidence:**
- src/telegram_bot/services/rate_limit.py:16-60 — `check_upload_rate_limit` defined with RATE_LIMIT_REQUESTS=10, RATE_LIMIT_PERIOD=60
- grep `check_upload_rate_limit` across all .py -> single match (only the definition)
- src/telegram_bot/handlers/ad_create.py:56-61 — imports `generate_storage_key, validate_photo, strip_photo_exif, delete_photo` from `telegram_bot.services.media` but NOT `check_upload_rate_limit` from `telegram_bot.services.rate_limit`
- src/telegram_bot/handlers/ad_create.py:646-720 — `process_photos` has no rate-limit call between download (686) and save (704)
- src/telegram_bot/services/__init__.py:3 — `__all__` exports only generate_storage_key/validate_photo/validate_jpeg_bytes; rate_limit is not re-exported, confirming it is dead to the upload flow

**Validator's Verification:**
- Read rate_limit.py in full (61 lines). Confirmed `check_upload_rate_limit` defined at line 26 with `RATE_LIMIT_REQUESTS: Final[int] = 10` (line 17) and `RATE_LIMIT_PERIOD: Final[int] = 60` (line 20). The function uses `cache.add` + `cache.incr` atomic pattern (lines 49-56), returns `True`/`False`.
- Grep `check_upload_rate_limit` across all `.py` files in `src/`: **1 match** — only the definition at rate_limit.py:26. Zero call sites anywhere in the codebase.
- Read ad_create.py:56-61 (imports). Confirmed imports from `telegram_bot.services.media` (generate_storage_key, validate_photo, strip_photo_exif, delete_photo). No import of `check_upload_rate_limit` from `telegram_bot.services.rate_limit`.
- Read ad_create.py:646-720 (process_photos). Confirmed the flow: download (line 686) → validate (line 695) → save (line 704) → append to state (line 708). No `check_upload_rate_limit` call anywhere in this path.
- Read services/__init__.py: confirmed `__all__ = ["generate_storage_key", "validate_photo", "validate_jpeg_bytes"]` — `rate_limit` is not re-exported, so it is not part of the public services API.
- Note: the rate_limit.py docstring states "Mirrors `apps.search.services.rate_limit` using Django's cache framework" — so a parallel rate limiter IS used in the search autocomplete path (search/services/rate_limit.py), but the bot upload rate limiter is dead code.

**Evidence Quality:** **High** — all claims verified exact.

**Recommendation:** [SPEC-DEVIATION] Wire `check_upload_rate_limit(user_id)` (resolved from the FSM/session user) into `process_photos` before `download_photo`, returning a Telegram message "uploading too fast, please wait" when it returns False. Add a unit test that calls it on a mocked cache and asserts the False path.

> **Validation Note:**
> - **Action:** none (validated as-is)
> - **Detail:** All claims verified exact. The function exists and is correctly implemented but has zero call sites.

---

### NEW-ME-007: `sweep_orphaned_media` command references non-existent `AdvisoryLockId.SWEEP_ORPHANED_MEDIA` [REJECTED-FOR-FINDING-STATUS]

> **Note:** This is a NEW finding discovered during validation of ME-002/ME-003. It does not replace either finding — it provides the missing context that explains why the orphan-reconciliation backstop is non-functional.

| Field | Value |
|-------|-------|
| **ID** | NEW-ME-007 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | src/backend/apps/media/management/commands/sweep_orphaned_media.py:87, src/backend/apps/core/enums.py:23-42 |
| **Validation Status** | **DETECTED** (root cause confirmed) |

**Description:** The `sweep_orphaned_media` management command (a store-vs-DB reconciliation that walks MEDIA_ROOT and deletes files with no matching AdImage row) references `AdvisoryLockId.SWEEP_ORPHANED_MEDIA` at line 87. This enum member is **not defined** in `AdvisoryLockId` (enums.py:23-42, which defines IDs 1-12, 10, 100-111). Calling `handle()` on this command would raise `AttributeError: SWEEP_ORPHANED_MEDIA` immediately, making the command non-functional. Additionally, the command is **not scheduled** in the hourly scheduler (`docker/entrypoint-scheduler.sh` lines 28-37 list 8 commands; `sweep_orphaned_media` is absent) and has **no tests** (`test_sweep_commands.py` and `test_sweep_lock_structure.py` do not reference it).

**Validator's Verification:**
- Read sweep_orphaned_media.py:87: `with advisory_lock(AdvisoryLockId.SWEEP_ORPHANED_MEDIA):`
- Read enums.py:23-42 (full AdvisoryLockId enum): members are ARCHIVE_SWEEP=1, DELETE_SWEEP=2, CONSENT_HARD_DELETE=3, SWEEP_DRAFTS=4, CLEANUP_LOGIN_TOKENS=5, PURGE_FAILED_ADS=6, PURGE_REJECTED_ADS=7, ROLLUP_DAILY_METRICS=8, ALERT_DELIVERY_TASK=9, QUEUE_PROCESSING=10, PURGE_DELETED_ADS=11, RECOMPUTE_NORMALIZED_PRICES=12, MIGRATE=100, CREATE_ADMIN=101, BACKFILL_THUMBNAILS=102, SEED=110, TEST_SCHEMA_SETUP=111. **`SWEEP_ORPHANED_MEDIA` is NOT present.**
- Grep `SWEEP_ORPHANED_MEDIA` across entire `src/`: 1 match (only sweep_orphaned_media.py:87, the broken reference).
- Grep `sweep_orphaned_media` across entire project root: 0 content matches outside the command file itself. The command is NOT referenced in `entrypoint-scheduler.sh`, `docker-compose.yml`, `docker-compose.prod.yml`, `Makefile`, or any management command list.
- Grep `test_sweep_orphan|TestSweepOrphan|orphaned_media` across `src/`: 0 matches. No tests exist for this command.
- Confirmed by reading `entrypoint-scheduler.sh`: hourly_commands list (lines 28-37) includes only: archive_sweep, delete_sweep, consent_hard_delete, sweep_drafts, cleanup_login_tokens, purge_failed_ads, purge_rejected_ads, purge_deleted_ads. `sweep_orphaned_media` is absent.

**Evidence Quality:** **High** — root cause confirmed at exact line reference.

**Recommendation:** Add `SWEEP_ORPHANED_MEDIA = 103` (or next free ID) to `AdvisoryLockId` in enums.py, and add `sweep_orphaned_media` to the hourly scheduler loop in `entrypoint-scheduler.sh`. Add a test in `test_sweep_lock_structure.py`. Additionally, the orphan sweep uses `os.remove` directly (not `delete_photo`) — consider routing through a shared safe-deletion primitive to inherit the containment check from ME-001.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 6 | ME-001, ME-002, ME-003, ME-004, ME-005, ME-006 |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |
| New findings (from validation) | 1 | NEW-ME-007: broken `sweep_orphaned_media` enum reference |

### Findings by Severity

| Severity | Count | IDs |
|----------|-------|-----|
| CRITICAL | 1 | ME-001 |
| HIGH | 4 | ME-002, ME-003, ME-004, ME-006 |
| MEDIUM | 1 | ME-005 |
| LOW | 0 | — |
| **Total** | **6** | |

### Evidence Quality Assessment

| ID | Evidence Quality | Notes |
|----|------------------|-------|
| ME-001 | **High** | All code claims verified at exact line numbers. Additional traversal vector discovered in `AdImage.save()` (models.py:584). The finding omitted `users/services/deletion.py` (line 158-159) as an affected module — it also calls `delete_photo` with unvalidated `image` keys. |
| ME-002 | **High** | Core claims verified exact: all 6 sweeps collect only `image` keys; grep confirms 0 `delete_photo(.*thumbnail` calls; thumbnails ARE stored in model fields. Important context: `sweep_orphaned_media.py` exists as a backstop but is broken (NEW-ME-007) and unscheduled, so the orphan problem is real in practice. |
| ME-003 | **Medium-High** | Core non-atomicity and swallowed-error claims verified exact in all 6 sweeps + deletion.py. However, two evidence claims are **factually incorrect**: (1) "no periodic store-vs-DB reconciliation job" is false — `sweep_orphaned_media.py` exists; (2) the grep claim "reconcile/dead_letter/orphan -> none found" is false (35 matches). Substance is correct because the orphan sweep is broken (NEW-ME-007) and unscheduled. Also: function name "hard_delete_user" is incorrect — the actual function is `withdraw_consent`. Partially duplicates Phase 03 DB-004 (same non-atomicity root cause). |
| ME-004 | **High** | All claims verified exact. The upload flow (download→validate→save→append) has no count cap before disk write; the 1-5 enforcement is post-hoc on "done"; the error message text confirmed inverted. |
| ME-005 | **High** | All claims verified exact. No `MAX_IMAGE_PIXELS` set anywhere (src grep + env var grep: 0 matches). Decode order confirmed: size cap → Image.open+exif_transpose → dimension check. |
| ME-006 | **High** | All claims verified exact. `check_upload_rate_limit` defined at rate_limit.py:26; grep confirms 0 call sites; ad_create.py imports do not include it; `services/__init__.py` `__all__` does not export it. |
| NEW-ME-007 | **High** | Root cause confirmed: `AdvisoryLockId.SWEEP_ORPHANED_MEDIA` not in enum (enums.py:23-42); command not scheduled (entrypoint-scheduler.sh:28-37); no tests. |

### Rejected Findings

None — all six findings are technically valid. ME-003 has inaccurate evidence claims but its core technical assertions (non-atomic DB/delete, swallowed errors) are verified and warrant remediation action.

### Merged Findings

None.

### Reclassified Findings

None. All Type fields (`RUNTIME-ERROR`) are preserved as-is per the exemplar pattern.

---

## Rollout Recommendations (Priority Order)

1. **ME-001 (CRITICAL) — Fix path traversal in `delete_photo`.** Add `os.path.realpath` containment check in `delete_photo` (media.py:101-104); add `RegexValidator`/`CheckConstraint` on `AdImage.image` and `thumbnail_*` fields matching `^[A-Za-z0-9._-]+(\/[A-Za-z0-9._-]+)*\.jpg$` to enforce the documented UUID+seed format at rest. Apply the same containment check to `AdImage.save()` (models.py:584) and `sweep_orphaned_media.py` (line 110). Atomic: modifies one function + model fields + import sites in the 6 sweep commands for the validator. **No runtime risk for valid keys.**

2. **NEW-ME-007 (HIGH) — Fix broken `sweep_orphaned_media` command.** Add `SWEEP_ORPHANED_MEDIA = 103` to `AdvisoryLockId` in `enums.py` and add `sweep_orphaned_media` to the hourly scheduler loop in `docker/entrypoint-scheduler.sh`. Add a test in `test_sweep_lock_structure.py`. **Critical prerequisite for ME-003's reconciliation backstop.**

3. **ME-004 (HIGH) — Enforce upload count cap at the edge.** Reject in `process_photos` before `download_photo` once `len(photos) >= 5`. Fix the inverted error message ("at least 1" → "at most 5"). Trivial change, zero runtime risk.

4. **ME-006 (HIGH) — Wire `check_upload_rate_limit` into `process_photos`.** Add `check_upload_rate_limit(user_id)` before `download_photo`. Requires resolving the user_id from FSM state (the bot session already has access to the user). Small but requires FSM-state plumbing.

5. **ME-003 (HIGH) — Escalate swallowed deletion failures.** After fixing NEW-ME-007, the orphan sweep provides crash-recovery reconciliation. Additionally: (a) escalate `delete_photo`'s exhausted-retry `logger.error` to a structured metric/event; (b) optionally introduce a `pending_media_deletion` dead-letter table for retry. Medium effort; should be done in the same PR as ME-001's `delete_photo` changes (both modify the same function).

6. **ME-002 (HIGH) — Collect thumbnail keys in sweeps.** Extend all 6 sweep commands + `soft_delete_user_ads` to collect `thumbnail_small/medium/large` alongside `image` and pass each to `delete_photo` (with the ME-001 containment check in place). Add reference-counting for shared seed thumbnails. Medium effort; depends on ME-001 (containment check must be in `delete_photo` first).

7. **ME-005 (MEDIUM) — Set `Image.MAX_IMAGE_PIXELS`.** Set project-wide (e.g. in bot `apps.py` `ready()`) to a value just above the 2560² ceiling. Small change; no runtime risk for valid images.

### Ordering Constraints

- **ME-001 must precede ME-002**: ME-002's recommendation passes thumbnail keys to `delete_photo`; the containment check from ME-001 must be in place first so that thumbnail keys (which include `-small`/`-medium`/`-large` suffixes and could theoretically be poisoned) are safe.
- **NEW-ME-007 must precede ME-003's reconciliation backstop**: ME-003's recommendation to rely on a reconciliation command depends on `sweep_orphaned_media` being functional.
- **ME-001 and ME-003 both modify `delete_photo`**: changes should be in the same PR to avoid merge conflicts.
- **ME-004 and ME-006 both modify `process_photos`**: independent changes but should be reviewed together for the upload flow.

### Unsafe Rollout Sequences

- Do NOT deploy ME-002 (collecting thumbnail keys in sweeps) without ME-001 (containment check in `delete_photo`) — passing unvalidated thumbnail keys to `delete_photo` without containment reintroduces the path traversal risk from ME-001.
- Do NOT schedule `sweep_orphaned_media` (NEW-ME-007) without fixing the enum reference — the command will crash with `AttributeError` on every invocation.
- The orphan sweep uses `os.remove` directly (not `delete_photo`) — consider routing through a shared safe-deletion primitive to inherit the ME-001 containment check.

## Warnings

| Risk | Description |
|------|-------------|
| **Non-scheduled orphan sweep** | `sweep_orphaned_media.py` exists as a file but is broken (non-existent enum member) and unscheduled. It provides no actual backstop for ME-002 or ME-003. Both findings' remediations should not depend on it until NEW-ME-007 is fixed and it's scheduled. |
| **Cross-phase duplication** | ME-003's non-atomicity claim duplicates Phase 03 (DB-004) which reached the same conclusion about `delete_sweep`/`sweep_drafts`/`consent_hard_delete`. Avoid redundant work — coordinate with the Phase 03 remediation plan. |
| **Path traversal in multiple code paths** | ME-001's root cause (unvalidated `image` field) manifests in at least 3 code paths: `delete_photo` (media.py:101), `AdImage.save()` (models.py:584), `_serve_image` (listings.py:109), and `sweep_orphaned_media` (line 110). Fixing only `delete_photo` leaves the other three vulnerable. The `RegexValidator`/`CheckConstraint` on the model field is the only holistic fix. |
| **Inverted error message** | ME-004's misleading "at least 1 photo" message when the count is >5 is a user-experience bug that could confuse sellers. Fix alongside the count cap. |
| **Thumbnail orphans during ad submission failure** | If thumbnail generation fails (ad_create.py:1189 `except Exception`), the photo dict sets thumbnail keys to None (lines 1195-1199), but the main image file is already on disk (saved at line 704). If the subsequent ad submission also fails, the main image file becomes orphaned with no cleanup path (only the main `image` key is collected by sweeps, and thumbnails were None). The orphan sweep would eventually reclaim the main image, but only if NEW-ME-007 is fixed. |

## Required Fixes

1. **ME-001**: Add `os.path.realpath` containment check in `delete_photo`; add `RegexValidator`/`CheckConstraint` on `AdImage.image` and all three `thumbnail_*` fields. Apply containment to `AdImage.save()` and `sweep_orphaned_media`'s `os.remove` path.
2. **NEW-ME-007**: Add `SWEEP_ORPHANED_MEDIA = 103` to `AdvisoryLockId`; schedule `sweep_orphaned_media` in hourly scheduler; add lock-structure test.
3. **ME-004**: Add `len(photos) >= 5` rejection before `download_photo` in `process_photos`; fix inverted error message.
4. **ME-006**: Wire `check_upload_rate_limit(user_id)` into `process_photos` before `download_photo`.

## Advisory Recommendations

1. **ME-005**: Set `Image.MAX_IMAGE_PIXELS` project-wide; prefer metadata-only dimension probe.
2. **ME-003**: After NEW-ME-007 is fixed, escalate `delete_photo`'s exhausted-retry path from `logger.error` to a structured metric/event. Consider a `pending_media_deletion` dead-letter table for automatic retry of failed deletions.
3. **ME-002**: After ME-001 and NEW-ME-007 are fixed, extend all 6 sweeps + `soft_delete_user_ads` to collect all 4 AdImage keys and delete each via `delete_photo`. Add reference-counting for shared seed thumbnails. Add regression test asserting thumbnail cleanup after sweep.
4. **Code health**: Extract `delete_photo` from `telegram_bot/services/media.py` into a backend-shared location (e.g. `apps/media/services/filesystem.py`) to resolve the dependency-direction violation noted in Phase 01 (ENT-001). All 7 production modules currently import it from the bot package.
```
