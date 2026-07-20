---
name: audit-findings
description: Structured findings template for audit phase output
agent: audit-executor
alwaysApply: false
---

# Phase 07 Audit Findings — Media Handling & Security

**Executor:** audit-executor (Kilo)
**Template:** .kilo/commands/audit/phases/07-audit-media.md
**Status:** complete
**Validated:** no

---

## Findings

### MED-001: nginx serves `/media/` directly with no per-request access control — unpublished/withdrawn/deleted ad photos are fetchable by URL

| Field | Value |
|-------|-------|
| **ID** | MED-001 |
| **Severity** | CRITICAL |
| **Type** | RUNTIME-ERROR / SPEC-DEVIATION |
| **Affected Modules** | `docker/nginx/nginx.conf` (location `/media/`), `src/backend/config/urls.py`, `src/backend/apps/ads/urls.py`, `src/backend/apps/ads/views/listings.py` |
| **Classification** | mandatory |

**Description:** All photo files live in a shared Docker volume (`media_volume`) and are served by nginx via `alias /media_volume/;` with no conditional logic (`nginx.conf:56-76`). There is no Django view that gates `/media/` by ad status — `config/urls.py` and `ads/urls.py` contain no media route; the app only ever *renders* `image.image_url` (`/media/<uuid>.jpg`) inside templates. nginx cannot query the DB, so it will serve any file present in the volume regardless of whether the owning ad is `DRAFT`, `ON_MODERATION`, `ON_MODERATION_FAILED`, `REJECTED`, `ARCHIVED`, `DELETED`, or belongs to a seller who revoked consent. The phase goal explicitly requires that unpublished/withdrawn/deleted-ad photos are NOT fetchable via direct URL; the current design fails this because the static layer has no per-request auth and the app never enforces it. The only thing protecting a photo is UUID-v4 unpredictability, which is "security by obscurity" — not access control.

**Evidence:**
- `docker/nginx/nginx.conf:56-76` — `location /media/ { alias /media_volume/; ... }` with no status check, no `internal`, no `X-Accel-Redirect` handoff.
- `src/backend/config/urls.py:10-18` — no media/serve route.
- `src/backend/apps/ads/urls.py:11-21` — no media route.
- `src/backend/apps/ads/views/listings.py:42-49` — `ad_detail` filters `status=AdStatus.PUBLISHED` for the *page*, but the `<img src>` URLs point straight at nginx-served files.
- `templates/ads/detail.html:36-39`, `templates/admin/moderation/review.html:78-83` (staff) — images referenced directly via `image.image_url`.

**Recommendation:** Introduce an app-level media gate. Either (a) move media serving behind a Django view that looks up the `AdImage` → `Ad`, asserts `status == PUBLISHED` (and, for staff, the moderation queue), opens the file with `django.http.FileResponse` / `sendfile`, and have nginx `proxy_pass` `/media/` to the web service (or use `internal` + `X-Accel-Redirect`); or (b) keep nginx `alias` only for a dedicated *published* subtree and physically move non-public photos out of the nginx-served root. The simplest low-risk option for this project: serve `/media/` through a small authenticated Django view (`X-Accel-Redirect` to an `internal`-marked nginx location) so the DB is consulted per request. Effort: medium. Priority: mandatory (CRITICAL per phase §8).

---

### MED-002: EXIF / metadata is never stripped — PII can persist in served image bytes

| Field | Value |
|-------|-------|
| **ID** | MED-002 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION / BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/services/media.py` (`save_photo`/bot path), `src/telegram_bot/handlers/ad_create.py:431-436` (`save_photo`) |
| **Classification** | mandatory |

**Description:** `save_photo` writes the Telegram-supplied bytes verbatim to `MEDIA_ROOT` (`ad_create.py:431-437`): `open(media_path,"wb").write(photo_bytes)`. Validation in `media.py::validate_photo` only does `Image.open(...)` (lazy, does not `load()`/`verify()`), so it never re-encodes or touches EXIF. Any GPS coordinates, device make/model, or timestamps embedded by the sender's camera remain in the stored JPEG and are delivered to every visitor via nginx. The phase lists "PII (EXIF/metadata) leaks in served image bytes" as CRITICAL. The architecture-testing plan (`docs`/`..._plan.md:253`) already flagged re-encode-on-store as a deferred "future risk" (decision E) — it must now be treated as a live finding, not deferred.

**Evidence:**
- `src/telegram_bot/handlers/ad_create.py:431-437` — `save_photo` writes `photo_bytes` as-is.
- `src/telegram_bot/services/media.py:54-66` — `validate_photo` uses `Image.open(io.BytesIO(photo_bytes))` then reads `.size`; no `img.load()`, no `ImageOps.exif_transpose`, no `img.save(...)` re-encode, no EXIF strip.
- `docs/01-spec/architecture-structure.md:46-48` — serves photos "as is" via `<img src>` (no transform step defined).

**Recommendation:** Re-encode the image on store: open with Pillow, call `ImageOps.exif_transpose`, drop all EXIF (`img.info.pop("exif", None)` / `img.save(..., "JPEG", exif=None, optimize=True)`), and write the re-encoded bytes. This also doubles as the malicious-JPEG decoder-hardening the plan recommends. Verify with `exiftool` on a seeded GPS-bearing file. Effort: small. Priority: mandatory (CRITICAL per phase §8).

---

### MED-003: Sweep / erasure commands delete DB rows but never delete physical media files (orphaned PII on disk)

| Field | Value |
|-------|-------|
| **ID** | MED-003 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR / BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/core/management/commands/delete_sweep.py`, `sweep_drafts.py`, `purge_rejected_ads.py`, `purge_failed_ads.py`, `consent_hard_delete.py` |
| **Classification** | mandatory |

**Description:** Every retention/erasure sweep relies on ORM `CASCADE` to remove `ad_images` rows, but no code path unlinks the corresponding files from `MEDIA_ROOT`. A repo-wide grep finds no `os.remove`/`unlink`/`shutil` for media anywhere in production code. The files remain in `media_volume` indefinitely and continue to be served by nginx (see MED-001). This violates the phase goals for storage hygiene (orphaned files), retention correctness (files not removed), and PII-erasure cascade (physical media remains after consent withdrawal). Phase 05 and Phase 06 audits already identified this; this phase owns the physical-removal mechanics and confirms it is still unaddressed.

**Evidence:**
- `delete_sweep.py:59-60`, `sweep_drafts.py:57-58`, `purge_rejected_ads.py:59-61`, `consent_hard_delete.py:70-71` — all `queryset.delete()` only; comments say "CASCADE will handle ad_images" with no filesystem unlink.
- `ad_create.py:431-436` — files written via `open(...,"wb")`; no symmetric delete helper exists.
- `src/telegram_bot/services/media.py` — exposes only `validate_*` and `generate_storage_key`; no `delete_photo`/`unlink`.
- Grep for `os.remove|os.unlink|shutil|rmtree` across `src/` returns zero production media deletions (only prior audit-notes text).

**Recommendation:** Add a single `delete_photo(storage_key)` helper (mirror of `save_photo`) that `os.remove`s `MEDIA_ROOT/<key>` inside a try/except `FileNotFoundError`. Wire it into each sweep so that, after collecting the target `AdImage.image` values (before `queryset.delete()`), files are unlinked; also call it from `consent_hard_delete` over the user's ads' images. To avoid deleting a file still referenced by another row, delete per `AdImage` row (not per ad) so FK semantics are preserved, and wrap row-delete + file-unlink so failures are logged. Reference-count only if dedup is ever introduced. Effort: small. Priority: mandatory (HIGH per phase §8; CRITICAL for the erasure sub-case MED-001-adjacent).

---

### MED-004: In-flight cancel / crash leaves orphaned partial files in MEDIA_ROOT

| Field | Value |
|-------|-------|
| **ID** | MED-004 |
| **Severity** | HIGH |
| **Type** | RUNTIME-ERROR |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py` (FSM photo step `:266-288`, commit `:547-554`), `src/telegram_bot/services/media.py` |
| **Classification** | mandatory |

**Description:** Photos are written to disk at upload time (`ad_create.py:281-282`) but the `AdImage` row is created only later at commit (`ad_create.py:548-554`). If the user cancels the dialog, the bot crashes, or a moderation failure occurs before commit, the already-written files are never referenced by any row and are never cleaned up. The phase edge case "Ad deleted while a photo upload is in flight → no orphaned partial file" and "Seller withdraws (erasure) mid-upload → files cleared" are not handled. Phase 05 (`findings.md:130-139`) already flagged that DRAFT-sweep cleanup does not unlink these. Combined with MED-003 (no unlink anywhere), every abandoned upload is permanent disk bloat and (per MED-001/MED-002) potentially PII-bearing.

**Evidence:**
- `src/telegram_bot/handlers/ad_create.py:280-288` — `save_photo` writes file; `storage_key` held only in FSM `state`, not persisted.
- `src/telegram_bot/handlers/ad_create.py:547-554` — `AdImage` rows created only on successful commit.
- `sweep_drafts.py` / `purge_failed_ads.py` — delete rows, never the orphaned files written pre-commit.
- `.ai/audit/05-ad-lifecycle/findings.md:130-139` — confirms orphan `media/` files on DRAFT sweep.

**Recommendation:** On FSM cancel/timeout, and in the DRAFT/failed sweeps, unlink every `storage_key` still held in `state`/orphaned rows (using the MED-003 helper). Alternatively, defer the physical write until commit (write bytes into a temp staging area, move to `MEDIA_ROOT` only when `AdImage` rows are created) so an aborted flow leaves no committed file. Effort: small. Priority: recommended (HIGH per phase §8).

---

### MED-005: Two divergent `generate_storage_key` implementations; docstring claims "ad_id + UUID v4" that neither honors

| Field | Value |
|-------|-------|
| **ID** | MED-005 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/ads/models.py:230-233` (`AdImage.generate_storage_key`), `src/telegram_bot/services/media.py:71-73` (`generate_storage_key`) |
| **Classification** | advisory |

**Description:** `AdImage.generate_storage_key()` returns `str(uuid.uuid4())` (36 chars, no extension). `telegram_bot.services.media.generate_storage_key()` returns `f"{uuid.uuid4()}.jpg"` (41 chars, with `.jpg`). Two functions with the same name/intent produce different key formats. The model's version lacks a file extension, so a row created with it would be served by nginx as `default_type application/octet-stream` (forced download, not inline) because the nginx MIME whitelist only maps `jpg`/`jpeg` → `image/jpeg` (`nginx.conf:71-75`). The `AdImage` docstring (`models.py:190-192, :231-232`) and the architecture doc claim the key is "ad_id + UUID v4 ... no PII", but no implementation prefixes `ad_id`, and the bot uses a bare UUID. Divergent generators are a maintenance trap and a latent serving bug.

**Evidence:**
- `src/backend/apps/ads/models.py:230-233` — `return str(uuid.uuid4())`.
- `src/telegram_bot/services/media.py:71-73` — `return f"{uuid.uuid4()}.jpg"`.
- `nginx.conf:71-75` — `types { image/jpeg jpg jpeg; }` + `default_type application/octet-stream`.
- `docs/01-spec/architecture-structure.md:46-48` and `.ai/plans/architecture_testing_plan.md:226` — claim "ad-scoped + UUID v4".

**Recommendation:** Make one canonical generator (keep the bot version's `<uuid>.jpg` form; it is what production uses) and have `AdImage.generate_storage_key` delegate to it, or remove the unused model method to avoid the divergent copy. Update the docstring to state the true format (bare UUID v4 + `.jpg`, no `ad_id` prefix). If `ad_id` scoping is actually desired for collision safety, implement it consistently. Effort: trivial. Priority: recommended.

---

### MED-006: Storage keys are not ad_id-scoped — UUID-v4 collision would silently overwrite an existing file

| Field | Value |
|-------|-------|
| **ID** | MED-006 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/services/media.py:71-73`, `src/telegram_bot/handlers/ad_create.py:431-437` |
| **Classification** | advisory |

**Description:** `save_photo` does `open(media_path,"wb")` with `media_path = MEDIA_ROOT/<uuid>.jpg` and no `os.path.exists` guard. Because keys are process-global UUIDs (not namespaced per ad), a theoretical UUID-v4 collision would overwrite a different ad's photo with no error, and the referenced `AdImage` rows would then point at the wrong bytes. The phase edge case "UUID collision (theoretical) → no `IntegrityError` fallback gap" calls this out. Probability is ~0 but the write is non-atomic and unguarded.

**Evidence:**
- `src/telegram_bot/handlers/ad_create.py:431-437` — unconditional `open(...,"wb")`.
- `.ai/plans/architecture_testing_plan.md:254` — notes collision-overwrites as accepted-but-flagged.

**Recommendation:** Open with `os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)` (or `pathlib.Path.write_bytes` after an existence check) so a collision raises instead of silently overwriting; on collision, regenerate the key. Effort: trivial. Priority: recommended.

---

### MED-007: No thumbnail/transform step and no `download` rate limiting / spam throttle on photo upload

| Field | Value |
|-------|-------|
| **ID** | MED-007 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py` (photo step `:256-292`), `src/telegram_bot/services/media.py` |
| **Classification** | advisory |

**Description:** Photo count is bounded at 1–5 only at the *page* (ad-detail template) and validated in `auto_moderation._validate_image_count` at submission, but the per-message handler (`ad_create.py:256-292`) accepts each `/done`-terminated photo with no per-user rate limit and no upper-bound re-check at the moment of receipt (it only reports `({len(photos)}/5)`). A bot spammer can send many photos; the FSM `photos` list is bounded only implicitly by later validation. There is no transform/thumbnail step (acceptable for phase 1), but there is also no per-user throttle on `download_photo` calls, so a flood of large downloads can pressure the bot process and Telegram API. The phase §4(1) requires "rapid spam → rejected with correct limit enforced" and §5(b) requires rate limits.

**Evidence:**
- `src/telegram_bot/handlers/ad_create.py:256-292` — receives photo, validates type/size/dimensions, appends to `photos` list; no rate limit; count cap only enforced downstream.
- `src/telegram_bot/services/media.py:27-68` — validates format/size/dimensions; no rate-limit hook.
- `nginx.conf` rate-limits only `/login/` and `/search/`; `/media/` and the bot (polling) are not throttled at the edge.

**Recommendation:** Enforce the 5-photo cap and a per-user/minute throttle directly in the photo handler (reject the 6th photo with the same message). Optionally add a simple in-FSM `rate_limit` timestamp check on `download_photo`. Effort: small. Priority: recommended.

---

### MED-008: No app-level media tests for access-control, EXIF stripping, or physical deletion

| Field | Value |
|-------|-------|
| **ID** | MED-008 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/ads/tests/`, `src/telegram_bot/` (no media tests), `src/backend/apps/core/tests/test_sweep_commands.py` |
| **Classification** | advisory |

**Description:** The only media-related tests are `test_sweep_commands.py` (which verify DB-row CASCADE, not file deletion) and use `AdImage.generate_storage_key()` in fixtures. There are no tests asserting: (a) a DRAFT/DELETED ad's `/media/<key>` returns 404/403, (b) EXIF is absent after `save_photo`, (c) sweep commands remove files from disk, or (d) path-traversal keys are rejected. The phase §4 runtime-verification matrix is therefore unverifiable in CI. Per the project rule "tests must be a trustworthy safety net," these gaps mean the most security-sensitive media behaviors are unguarded.

**Evidence:**
- `src/backend/apps/ads/tests/` contains only `test_search_triggers.py`.
- `src/backend/apps/core/tests/test_sweep_commands.py:160,173,194` — assert rows gone, never touch `MEDIA_ROOT`.
- No `test_media*.py` anywhere in the repo (filesystem search returned none).

**Recommendation:** Add a `tests/test_media_security.py` that uses an isolated `MEDIA_ROOT` (settings override / tmp_path) and asserts: unpublished-ad photo not served (when MED-001 is fixed), EXIF stripped after store, sweep unlinks files, and crafted/encoded keys are rejected. Effort: medium. Priority: recommended.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2 |
| HIGH | 2 |
| MEDIUM | 3 |
| LOW | 1 |

## Mandatory Fixes

- **MED-001** — App-level access control for `/media/` (unpublished/withdrawn/deleted photos currently fetchable by URL).
- **MED-002** — Strip EXIF/metadata on store (re-encode via Pillow).
- **MED-003** — Delete physical media files in all sweeps + consent hard-delete.
- **MED-004** — Clean up orphaned partial files on FSM cancel/crash and in DRAFT/failed sweeps.

## Advisory Recommendations

- **MED-005** — Unify divergent `generate_storage_key` implementations; fix docstring ("ad_id + UUID v4" is inaccurate).
- **MED-006** — Guard `save_photo` against collision-overwrite (O_EXCL).
- **MED-007** — Enforce 5-photo cap + per-user throttle at the upload handler; rate-limit downloads.
- **MED-008** — Add media security tests (access control, EXIF, physical deletion, traversal).

## Doc Updates Needed

- **MED-005** — `docs/01-spec/architecture-structure.md:46-48` and `.ai/plans/architecture_testing_plan.md:226` claim keys are "ad-scoped + UUID v4"; reality is bare UUID v4 (+ `.jpg` from the bot generator). Update to reflect actual format or implement ad-scoping.
- **DOC-UPDATE** — `docs/01-spec/architecture-structure.md:46-48` states photos are served "as is" via `<img src>`; this should document the planned EXIF-strip + app-gated serving once MED-001/MED-002 land, so the doc does not describe a permanently-insecure design as intended.
