---
# Report metadata — fill once per phase report.
phase: "07"
phase_name: "media"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: ""  # Phase 99 only — omit/blank for raw phase findings
mode: "problems-only"
# Correct prefix per phase: 01-ENT, 02-CFG, 03-DB, 04-AUT, 05-AD, 06-PII, 07-MED, 08-SRH, 09-EXT, 10-QLT, 11-TST, 12-OPS, 13-PERF, 14-I18N
id_prefix: "MEDIA-"
# report_status = lifecycle of the report document (draft → validated)
# per-finding Status (in Findings Summary + field table below) = lifecycle of the individual finding (Open → Validated/Rejected/Merged/Reclassified/Deferred)
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/07-audit-media.md#severity-taxonomy"
---

# Audit Findings — MEDIA

> **Finding-ID prefix note.** `.kilo/commands/audit/phases/07-audit-media.md` §10 and
> `templates/audit-findings.md` both specify `MED-` / `07-MED`. The executing task
> instruction overrode this with `MEDIA-` ("Use your `MEDIA-` prefix"). `MEDIA-` is
> used throughout this report. Phase 99 must preserve these IDs verbatim; do not
> renumber to `MED-NNN`.

## Executive Summary

Photos are ingested, stripped of hidden location/device data, and served through a
well-built access gate — that part of the system is genuinely solid, and unpublished
or withdrawn listings are confirmed not to be reachable by direct link. The problems
are in what happens to files *after* they are stored. A seller's own ordinary action
(running `/post` a second time) can permanently delete the photographs of a live,
published listing, and several background cleanup jobs can delete or strand files that
other parts of the system still believe exist. Net effect: buyers see broken images on
live ads, and automated "privacy erasure" and "clean up old files" routines can
over-delete. **Eleven issues: 1 critical, 3 high, 5 medium, 2 low.** The critical one needs an
architecture-level change to how the system tracks who owns a photo.

## Scope & Methodology

**Scope:** `src/backend/apps/media` (models, schemas, `signals.py`, `services/filesystem.py`,
`services/thumbnails.py`, `services/hash_service.py`, `apps.py`, both management commands,
tests), plus every caller that creates, mutates or deletes `AdImage` rows and storage keys —
`apps/ads/services/{submission,images,copy_service}.py`, `apps/ads/views/{listings,edit}.py`,
`apps/ads/models.py` (`AdImage`), `apps/ads/admin.py`, `apps/users/services/deletion.py`,
`apps/core/management/commands/{sweep_orphaned_media,consent_hard_delete,purge_*,delete_sweep}.py`,
`apps/seed/generators/images.py`, `src/telegram_bot/{handlers/ad_create,services/ad_data}`,
`docker/nginx/nginx{,.dev}.conf`, and the media sections of `docs/01-spec` /
`docs/02-database`.

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | `media_gate` serves PUBLISHED media and 403s every non-published status | probe `audit07_probe.py` R-1, 7 statuses, `DEBUG=False` | PASS |
| R-02 | Staff bypass, declined-seller hiding, withdrawn-seller hiding | probe R-1 | PASS |
| R-03 | `Cache-Control: no-store` on 200, absent on 404, `Vary: Cookie` present | probe R-1 | PASS |
| R-04 | 7 crafted traversal/control-char keys rejected with 404 (no 500, no escape) | probe R-2 | PASS |
| R-05 | `assert_storage_key_contained` raises on `..`, absolute, NUL | probe R-2 | PASS |
| R-06 | EXIF/GPS/Make/DateTimeOriginal/JPEG-comment/XMP all absent after `strip_photo_exif` | probe R-3 (synthetic JPEG, Pillow `getexif()` + raw marker scan) | PASS |
| R-07 | Generated thumbnails carry no EXIF/comment | probe R-3 | PASS |
| R-08 | Shipped `media/seed/apartments_04.jpg` has no APP1/APP2/COM segment | host byte scan + JPEG segment walk | PASS |
| R-09 | `validate_photo` rejects PNG/PDF/oversize/over-dimension/truncated; accepts 2560×2560 | probe R-10 | PASS |
| R-10 | All `AdImage.image` keys are UUID v4 and match `KEY_FORMAT_REGEX` | probe R-9 | PASS |
| R-11 | Re-uploading identical bytes to a 2nd ad → 2nd ad gets 0 images, file orphaned | probe R-4 | **FAIL** → MEDIA-002 |
| R-12 | `copy_ad` shares keys; hard-deleting the source deletes the copy's files | probe R-5 | **FAIL** → MEDIA-001 |
| R-13 | Bot `/post` (`create_draft_ad`) hard-deletes a DRAFT sharing keys with a PUBLISHED ad → PUBLISHED ad's photos deleted, rows survive | probe #2 R-12, real `create_draft_ad` | **FAIL** → MEDIA-001 |
| R-14 | Orphan sweep preserves a just-promoted, not-yet-referenced file | probe R-7 | **FAIL** → MEDIA-003 |
| R-15 | Staging files excluded from the orphan sweep and reclaimed only by the 2 h TTL | probe R-7 | PASS |
| R-16 | `backfill_thumbnails` repairs a row whose thumbnails are partially present | probe R-6 | **FAIL** → MEDIA-004 |
| R-17 | Store↔DB diff after all operations: 0 orphan files, 0 dangling rows | probe R-8 | **FAIL** (5 dangling) → MEDIA-001 |
| R-18 | DRAFT-ad media removed on `withdraw_consent`; PUBLISHED media erased by `consent_hard_delete` after 30 d | probe R-11 | PASS |
| R-19 | Thumbnail keys of a DRAFT ad are 403 for anonymous and for the owning seller | probe #2 R-13 | PASS |
| R-20 | Media quality gates | `ruff check` + `basedpyright` over the media surface; 133 media/security tests | PASS (0 errors, 0 findings) |

> PASS results prove the audit was thorough; they are METHODOLOGY evidence, NOT findings.

**Tools used:** `docker compose … run` inside `mko-bazuna-test` (PostgreSQL 18 on host :5433);
two throwaway probe scripts under `.ai/tmp/` (both deleted at the end, both scratch
databases `audit07_probe` / `audit07_probe2` dropped); Pillow + Django test `Client` +
management-command `call_command`; host-side byte scan of the shipped seed JPEG;
`ruff`, `basedpyright`; `pytest` (media + media-security + bot photo suites).

**Assumptions:**
1. The `mko-bazuna-dev` web/bot containers are crash-looping (CFG-006), so no live reverse
   proxy was available; all HTTP evidence comes from Django's test client against the real
   URLconf, middleware and view code with `DEBUG=False` (the production `X-Accel-Redirect`
   branch). nginx behaviour itself was assessed by reading `docker/nginx/nginx*.conf`, not
   by issuing requests through it.
2. PostgreSQL 18, Django 5.2, `config.settings.test`, `DEBUG=False` overridden per-check.
3. `MEDIA_ROOT` was a per-run `tempfile.mkdtemp()`; no real media file was read, written or
   deleted. Every probe tore down its scratch database and temp `MEDIA_ROOT` in a `finally`-style
   tail block.
4. The pre-existing leftovers in `.ai/tmp/` (`probe_run{,2,3,4}.py`, `probe_setup.py`, database
   `audit05v_probe`) belong to another owner and were left untouched.

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| MEDIA-001 | Storage keys have no owner or reference count; deleting one ad destroys another live ad's photos | CRITICAL | Open | Data integrity / Architecture |
| MEDIA-002 | Per-seller content dedup silently drops the second ad's photo and orphans the whole file set | HIGH | Open | Correctness |
| MEDIA-003 | Hourly orphan sweep deletes files an in-flight upload has just promoted but not yet referenced | HIGH | Open | Data integrity |
| MEDIA-004 | Thumbnail generation is not atomic; a partial set permanently blocks the repair command | HIGH | Open | Reliability |
| MEDIA-005 | No way for a seller or a moderator to remove a single bad photo from a live ad | MEDIUM | Open | Operability / Spec deviation |
| MEDIA-006 | `/media/` is unrated and the nginx script-execution block documented in the spec does not exist | MEDIUM | Open | Security hardening / Spec deviation |
| MEDIA-007 | Staging churn has no disk quota; the 2 h TTL bounds residence time, not the rate | MEDIUM | Open | Availability |
| MEDIA-008 | Seed pipeline records thumbnail keys that were never written, and `seed/` is exempt from the orphan sweep | MEDIUM | Open | Data integrity |
| MEDIA-009 | No documented storage-key ownership model; the DB docs assert a key structure the code does not produce | MEDIUM | Open | Documentation |
| MEDIA-010 | `MediaDeletionError` escalation table is write-only — no reader, no retention, no admin | LOW | Open | Observability |
| MEDIA-011 | Stored originals are re-encoded at Pillow's default quality 75 with no documented rationale | LOW | Open | Maintainability / Documentation |

## Distribution

**Severity counts**

| CRITICAL | HIGH | MEDIUM | LOW |
|----------|------|--------|-----|
| 1 | 3 | 5 | 2 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 11 |

## Findings by Severity

### CRITICAL

#### MEDIA-001: [CRITICAL] — Storage keys have no owner or reference count; deleting one ad destroys another live ad's photos

| Field | Value |
|---|---|
| **ID** | MEDIA-001 |
| **Title** | Storage keys have no owner or reference count; deleting one ad destroys another live ad's photos |
| **Severity** | CRITICAL |
| **Category** | Data integrity / Architecture |
| **File(s)** | `src/backend/apps/media/signals.py:21-40`, `src/backend/apps/ads/services/copy_service.py:58-68`, `src/backend/apps/ads/services/images.py:62-78`, `src/telegram_bot/services/ad_data/orm.py:55-57` |
| **Status** | Open |
| **Problem** | The media layer assumes every `storage_key` has exactly one owner, but two production code paths create keys that are referenced by more than one `AdImage` row, and the deletion signal honours that assumption literally. `delete_adimage_files_on_delete` collects `instance.storage_keys()` at `pre_delete` time and calls `delete_photo(key)` for every one of them with no check that another row still references the same key. `copy_ad` creates new `AdImage` rows pointing at the *same* files, and `AdImageService.create_or_skip` can return an existing row while the caller writes a new file under a fresh key. The trigger is not exotic: the bot's `/post` handler (`create_draft_ad`) hard-deletes the seller's existing `DRAFT` ad, which CASCADE-deletes its `AdImage` rows and fires the signal. A `DRAFT` produced by `copy_ad` shares its keys with the `PUBLISHED` source ad, so `/post` destroys the source ad's photographs. The `AdImage` rows of the live ad survive; only the bytes disappear. |
| **Impact** | Buyers browsing the public site see broken images on a live, published listing, permanently, with no operator-visible error and no automatic repair — `sweep_orphaned_media` only removes unreferenced *files*, never re-creates missing ones, and `backfill_thumbnails` only regenerates *thumbnails*, never the original. The same mechanism means a seller's consent-withdrawal hard-delete (`consent_hard_delete`) can delete files belonging to an unrelated ad. Because `db-retention.md:102` and `technical-specification.md:88` both promise that erasure "removes physical ad-image files", operations and privacy reviewers are told the cascade is complete when it is in fact both incomplete and over-reaching. |
| **Root Cause** | The storage key is treated as an identity (`<uuid>.jpg`) but is used as a *value* with structural sharing. There is no entity that owns the bytes, no reference count, and no invariant tying a key to the ad that created it — so any consumer is free to duplicate the reference and any deleter is free to free it. `db-schema.md:320-321` states keys are "ad-scoped", which is what the signal implicitly relies on; the code has never enforced or documented that. |
| **Recommendation** | Decide the ownership model in the media layer and make it explicit. Cheapest correct option for this codebase: keep one physical file per upload and make `AdImage.image` *exclusive* — `copy_ad` copies the file (or re-uses the source row via an explicit link) instead of aliasing the key, and `create_or_skip` returns a value the caller must act on (see MEDIA-002). If structural sharing is wanted (it saves disk for `copy_ad`), introduce a `MediaObject`/blob row that owns the bytes with a `ref_count`, make every key resolve through it, and have `pre_delete` decrement-and-delete-at-zero. Add a `CHECK`-level or test-level invariant "every storage key is referenced by exactly one `AdImage` row, except `seed/`" and a store↔DB reconciliation test that fails on any dangling row. |
| **Effort** | M |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **CWE** | CWE-672 (Operation on a Resource after Expiration or Release) |
| **Likelihood** | HIGH |

| Field | Value |
|---|---|
| **Related Findings** | AD-003 (phase 05 filed the `copy_ad` reuse from the `Ad` side), ENT-009 (phase 01, locking — see MEDIA-003), MEDIA-002, MEDIA-009 |

**Evidence — `src/backend/apps/media/signals.py:21-40`** *(supports: "deletes every key of the row being deleted, with no check that another row still references the same key")*:
```python
@receiver(pre_delete, sender=AdImage)
def delete_adimage_files_on_delete(sender, instance, **kwargs):
    keys = list(instance.storage_keys())
    if not keys:
        return

    def _cleanup() -> None:
        for key in keys:
            try:
                delete_photo(key)
            except Exception:  # noqa: BLE001 — never let FS failure break the cascade
                logger.exception("Failed to delete media file for key: %s", key)

    transaction.on_commit(_cleanup)
```

**Evidence — `src/backend/apps/ads/services/copy_service.py:58-68`** *(supports: "two `AdImage` rows can hold the same storage key")*:
```python
        # Copy images (new rows, same storage keys — no file duplication)
        for img in source.images.all():
            AdImage.objects.create(
                ad=new_ad,
                image=img.image,
                telegram_file_id=img.telegram_file_id,
                position=img.position,
                thumbnail_small=img.thumbnail_small,
                thumbnail_medium=img.thumbnail_medium,
                thumbnail_large=img.thumbnail_large,
            )
```

**Evidence — `src/telegram_bot/services/ad_data/orm.py:55-57`** *(supports: "the trigger is an ordinary `/post`, not a race")*:
```python
            existing = Ad.objects.filter(user_id=user_id, status=AdStatus.DRAFT)
            if existing.exists():
                existing.delete()
```

**Evidence — probe #2 R-12, real `create_draft_ad` against a scratch DB + temp `MEDIA_ROOT`** *(supports: "a live PUBLISHED ad's four photo files are deleted while its `AdImage` row survives")*:
```text
  PUBLISHED ad #1 owns keys ['a22a4ee3-…-4e752b1fa9d.jpg', '…-small.jpg', '…-medium.jpg', '…-large.jpg']
  DRAFT copy    #2 reuses keys ['a22a4ee3-…-4e752b1fa9d.jpg']
  on disk before /post: {'…jpg': True, '…-small.jpg': True, '…-medium.jpg': True, '…-large.jpg': True}
  /post created a fresh DRAFT #3; old DRAFT copy #2 hard-deleted
  DRAFT copy rows remaining: 0
  PUBLISHED ad #1 rows remaining: 1
  on disk after /post:  {'…jpg': False, '…-small.jpg': False, '…-medium.jpg': False, '…-large.jpg': False}
[R12.PHOTOS_DELETED] /post deleted the PUBLISHED ad's photo files: PASS
[R12.ROWS_DANGLING] PUBLISHED ad's AdImage rows now point at deleted files: PASS
```

**Evidence — probe R-8, store↔DB diff after the full run** *(supports: "the store/DB reconciliation required by the phase rubric is not clean")*:
```text
  files on disk (non seed/staging) = 40
  ORPHAN FILES (no AdImage row)   = 0
  DANGLING ROWS (file missing)    = 5
    - eda60ef1-2f63-475e-aec8-35d218b97f19.jpg          <- copy_ad, source hard-deleted
    - eda60ef1-2f63-475e-aec8-35d218b97f19-small.jpg
    - eda60ef1-2f63-475e-aec8-35d218b97f19-medium.jpg
    - eda60ef1-2f63-475e-aec8-35d218b97f19-large.jpg
    - 85bbd96e-88cf-4bf7-96f9-e6aedb8e1f8c.jpg          <- /post cascade, PUBLISHED ad
```

---

### HIGH

#### MEDIA-002: [HIGH] — Per-seller content dedup silently drops the second ad's photo and orphans the whole file set

| Field | Value |
|---|---|
| **ID** | MEDIA-002 |
| **Title** | Per-seller content dedup silently drops the second ad's photo and orphans the whole file set |
| **Severity** | HIGH |
| **Category** | Correctness |
| **File(s)** | `src/backend/apps/ads/services/images.py:62-78`, `src/backend/apps/ads/services/submission.py:141-166`, `src/backend/apps/ads/services/submission.py:218-227` |
| **Status** | Open |
| **Problem** | `AdImageService.create_or_skip` looks for any `AdImage` of the *same seller* with a matching `sha256` and, on a hit, returns that existing row instead of creating one. It never creates a row for the ad being submitted, and `submit_ad` discards the return value (`AdImageService.create_or_skip(...)` at `:219` is not assigned). So when a seller reuses a photo they already posted on another ad, the new ad is published with **zero** images, the caller never learns why, and the freshly staged original plus its three generated thumbnails (≈4 files) are promoted to permanent storage with no row referencing them. Nothing rejects the ad; the seller gets a photo-less listing and no error. |
| **Impact** | A legitimate, spec-supported action (reposting the same photo on a second ad — the classifieds norm) silently produces an ad with no photo, contradicting spec `technical-specification.md:149` ("1–5 mandatory … cannot publish without ≥1 photo"). Each occurrence leaks 4 files to disk, reclaimed only by the hourly orphan sweep, and the "AdImage dedup: … skipped" INFO log at `images.py:70-77` is the only trace. |
| **Root Cause** | `create_or_skip` conflates two different things: "this seller already has this photo" (a storage-dedup fact) and "this ad already has this photo" (the actual write it was asked to perform). The dedup scope is the seller, the caller needs it to be the ad. The function's return type also hides the skip from a caller that does not check it. |
| **Recommendation** | Make the dedup scope the *target ad* (`AdImage.objects.filter(sha256=..., ad=ad)`), so a reposted photo on a new ad creates its own row and the file is correctly referenced. If cross-ad storage dedup is genuinely wanted, keep the storage-dedup but make the caller's contract explicit: have `create_or_skip` return a small result object (`created: bool`, `row: AdImage`) and have `submit_ad` (a) reject or warn when `created is False`, and (b) delete the promoted files it just staged. Add a test that submits identical bytes to two ads and asserts both ads end up with one image and zero orphans. |
| **Effort** | S |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **CWE** | CWE-459 (Incomplete Cleanup) |
| **Likelihood** | HIGH |

| Field | Value |
|---|---|
| **Related Findings** | MEDIA-001, AD-003 |

**Evidence — `src/backend/apps/ads/services/images.py:62-78`** *(supports: "dedup scope is the seller, and the existing row is returned instead of a row for the ad being written")*:
```python
        sha256 = cls._compute_sha256(image)

        if sha256:
            duplicate = AdImage.objects.filter(
                sha256=sha256,
                ad__user_id=ad.user_id,
            ).first()
            if duplicate is not None:
                logger.info(
                    "AdImage dedup: sha256=%s ad_id=%s user_id=%s "
                    "skipped (existing pk=%s)",
                    sha256[:12], ad.pk, ad.user_id, duplicate.pk,
                )
                return duplicate
```

**Evidence — `src/backend/apps/ads/services/submission.py:218-227`** *(supports: "the caller discards the return value, so the skip is invisible")*:
```python
        # Create AdImage records with pre-generated thumbnails
        for photo in input.photos:
            AdImageService.create_or_skip(
                ad=ad,
                image=photo.storage_key,
                telegram_file_id=photo.telegram_file_id,
                position=photo.position,
                thumbnail_small=photo.thumbnail_small,
                thumbnail_medium=photo.thumbnail_medium,
                thumbnail_large=photo.thumbnail_large,
            )
```

**Evidence — probe R-4, identical bytes to a second ad** *(supports: "the second ad receives no image and its file is orphaned")*:
```text
  ad_b images count = 0
  returned pk=13 belongs_to_ad=13 (ad_a=13 ad_b=14)
[R4.SECOND_AD_EMPTY] second ad receives NO image row: PASS
[R4.RETURNED_IS_OTHER_AD] returned row belongs to the FIRST ad: PASS
[R4.ORPHAN] second ad's file left unreferenced on disk: PASS
```

---

#### MEDIA-003: [HIGH] — Hourly orphan sweep deletes files an in-flight upload has just promoted but not yet referenced

| Field | Value |
|---|---|
| **ID** | MEDIA-003 |
| **Title** | Hourly orphan sweep deletes files an in-flight upload has just promoted but not yet referenced |
| **Severity** | HIGH |
| **Category** | Data integrity |
| **File(s)** | `src/backend/apps/media/management/commands/sweep_orphaned_media.py:41-50`, `:137-165`, `src/backend/apps/ads/services/submission.py:161-169` |
| **Status** | Open |
| **Problem** | `submit_ad` promotes the staged files to permanent `MEDIA_ROOT` at `:166`, *before* entering `transaction.atomic()` at `:169`, and deliberately takes no `AdvisoryLockId.SWEEP_ORPHANED_MEDIA` (103). `sweep_orphaned_media` runs hourly, holds lock 103, builds its `referenced` set from `AdImage` rows only, and deletes `on_disk - referenced`. A file that has been promoted but whose `AdImage` row has not committed is, by definition, in that difference. The scheduler runs the sweep once an hour, so this window is not a microsecond race — it is up to an hour wide and recurs every hour. |
| **Impact** | A live ad permanently points at a missing file: the listing renders a broken image and there is no self-healing path, because the orphan sweep only deletes files and `backfill_thumbnails` only regenerates thumbnails — never an original. The failure is silent (the sweep logs a success line), and it happens on the seller's most latency-sensitive action (submitting an ad for moderation). |
| **Root Cause** | The sweep's correctness rule is "`not in the DB` ⇒ orphan", but the promotion path deliberately creates a window in which the filesystem is ahead of the database. The staging subdirectory was created precisely to hold that window, but `move_staging_to_permanent` closes it by renaming the file *out* of the protected prefix before the row exists. |
| **Recommendation** | Keep the file inside a protected namespace until the row is committed. Either (a) leave the promoted originals under `staging/` and let a post-commit step rename them (so the sweep's `staging/` exclusion covers the whole window), or (b) widen the reference snapshot to include keys whose `mtime` is newer than the sweep start (a grace period), which is the smallest change and needs no new locking. Also stop trusting `delete_photo`'s success for reporting: count real removals. |
| **Effort** | S |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **CWE** | CWE-367 (Time-of-check Time-of-use Race Condition) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | ENT-009 (phase 01 filed the locking half; the filesystem consequence is owned here), DB-005 (phase 03 filed the snapshot→walk→unlink window), MEDIA-001 |

**Evidence — `src/backend/apps/ads/services/submission.py:161-169`** *(supports: "promotion happens outside the transaction, with no lock")*:
```python
    # Promote staging files to permanent storage BEFORE the transaction.
    # Thumbnailing already wrote staging/<uuid>-*.jpg variants; this moves the
    # original + all thumbnails to permanent MEDIA_ROOT so AdImage rows (in the
    # TX below) reference permanent keys.  On DB rollback the permanent files
    # become unreferenced orphans reclaimed by the normal orphan sweep.
    move_staging_to_permanent(input.photos)

    # DB transaction: save + images + status transition
    with transaction.atomic():
```

**Evidence — `src/backend/apps/media/management/commands/sweep_orphaned_media.py:139-142`** *(supports: "the rule is `not in the DB` ⇒ orphan")*:
```python
                referenced = _collect_referenced_keys()
                on_disk = set(_walk_media_files(media_root))

                orphans = on_disk - referenced
```

**Evidence — probe R-7, `manage.py sweep_orphaned_media` against a file promoted-but-unreferenced** *(supports: "the sweep deletes it")*:
```text
Deleted 1 orphaned media files.
  in-flight promoted file survives sweep = False (AdImage rows before/after 12/12)
[R7.SWEEP] orphan sweep preserves a just-promoted, not-yet-committed file: FAIL
```

**Evidence — `src/backend/apps/core/utils/scheduler.py:57-64`** *(supports: "the window recurs every hour")*:
```python
    "delete_sweep",
    "consent_hard_delete",
    "sweep_drafts",
    "sweep_orphaned_media",
    "cleanup_login_tokens",
```

---

#### MEDIA-004: [HIGH] — Thumbnail generation is not atomic; a partial set permanently blocks the repair command

| Field | Value |
|---|---|
| **ID** | MEDIA-004 |
| **Title** | Thumbnail generation is not atomic; a partial set permanently blocks the repair command |
| **Severity** | HIGH |
| **Category** | Reliability |
| **File(s)** | `src/backend/apps/media/services/thumbnails.py:74-100`, `src/backend/apps/ads/services/submission.py:141-159`, `src/backend/apps/media/management/commands/backfill_thumbnails.py:195-204` |
| **Status** | Open |
| **Problem** | `generate_thumbnails` writes the three variants in a loop with `os.open(..., O_CREAT|O_EXCL|O_WRONLY)`. If it dies part-way (ENOSPC, EIO, a killed worker) the already-written files stay on disk and the caller sees an exception. `submit_ad:153-159` catches every exception, sets all three `thumbnail_*` fields to `None` and continues — then `move_staging_to_permanent` still promotes the surviving files. The `AdImage` row is created with `NULL` thumbnails while two files exist on disk and no row references them. `backfill_thumbnails` cannot fix this: its `_read_and_generate` calls `generate_thumbnails` again, which raises `FileExistsError` on the *first* size, and the handler logs "already exist for AdImage %d (race), skipping" and returns `None` — forever, for every future run. |
| **Impact** | An ad permanently loses its thumbnails (the listing grid and gallery fall back to the full-size original — a bandwidth and layout regression that no test or dashboard detects), while the disk keeps two unreferenced files per occurrence. The documented self-healing command reports success while making no progress, so an operator running it repeatedly sees the same "N records need backfill" count forever. |
| **Root Cause** | "Generate all three or none" is not an invariant anywhere: the writes are individually `O_EXCL` with no rollback, and the *same* `O_EXCL` flag is reused as the backfill's idempotency guard, so a leftover file is indistinguishable from a legitimate race to the repair path. |
| **Recommendation** | Make generation transactional on disk: write each variant to a temp file in the same directory and `os.replace` it into place only after all three succeed, unlinking partials on failure. Then make the backfill's guard distinguish the two cases — if a target file already exists *and* the row's field is NULL, delete the stale file and regenerate rather than skipping. Reuse that same guard in `ImageGenerator._preprocess_one` (MEDIA-008). |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-459 (Incomplete Cleanup) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | MEDIA-008, MEDIA-003 |

**Evidence — `src/backend/apps/media/services/thumbnails.py:91-98`** *(supports: "each variant is written independently; no rollback on failure")*:
```python
            fd = os.open(
                target_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
            try:
                os.write(fd, buffer.getvalue())
            finally:
                os.close(fd)

        return thumbnails
```

**Evidence — `src/backend/apps/ads/services/submission.py:153-159`** *(supports: "the failure is swallowed and the row is written with NULL thumbnails")*:
```python
        except Exception:
            logger.exception(
                "Failed to generate thumbnails for %s", photo.storage_key
            )
            photo.thumbnail_small = None
            photo.thumbnail_medium = None
            photo.thumbnail_large = None
```

**Evidence — probe R-6, exactly the state a mid-loop failure leaves behind** *(supports: "backfill cannot repair it, and the leftover files stay unreferenced")*:
```text
  state: files ['…-small.jpg', '…-medium.jpg'] exist, row thumbnails all NULL
  after backfill run #1: small=None medium=None large=None
  unreferenced leftover files after backfill: ['…-small.jpg', '…-medium.jpg']
[R6.BACKFILL_BLOCKED] backfill CANNOT repair a partially-thumbnailed row: PASS
[R6.ORPHAN_LEFTOVER] O_EXCL leaves unreferenced thumbnail files behind: PASS
Deleted 3 orphaned media files.
  leftover files after orphan sweep: []
  after backfill run #2 (post-sweep): small=…-small.jpg large=…-large.jpg
[R6.REPAIRABLE] backfill repairs the row once the orphans are swept: PASS
```

---

### MEDIUM

#### MEDIA-005: [MEDIUM] — No way for a seller or a moderator to remove a single bad photo from a live ad

| Field | Value |
|---|---|
| **ID** | MEDIA-005 |
| **Title** | No way for a seller or a moderator to remove a single bad photo from a live ad |
| **Severity** | MEDIUM |
| **Category** | Operability / Spec deviation |
| **File(s)** | `src/backend/apps/ads/admin.py:188-198`, `src/backend/apps/ads/views/edit.py:169`, `docs/01-spec/technical-specification.md:76` |
| **Status** | Open |
| **Problem** | `technical-specification.md:76` states "Phase-1 moderation is text-only (US-A10). Bad photos removed manually by moderator (incl. account ban)." No such control exists. `AdImageAdmin` sets `has_add_permission`, `has_change_permission` and `has_delete_permission` all to `False`, so the Django admin can neither unlink nor replace a photo. The seller-facing edit form submits `photos=[]` on both branches that reach `submit_ad` (`edit.py:169`, `:212`), so it has no photo controls, and `edit.py:154` documents "Price/photo edits" as a supported action that the code does not implement. The bot has no per-photo delete handler — `cmd_cancel` only bulk-cleans a DRAFT. |
| **Impact** | A photo containing a phone number, a face, or anything else that must come off a live ad can only be removed by deleting or archiving the whole ad. That is disproportionate (it also destroys the seller's text, views and analytics), it is the exact scenario the spec anticipated, and — per MEDIA-001 — the ad-lifecycle routes that *do* exist can delete files belonging to other ads. Moderators are left with a ban-or-nothing response. |
| **Root Cause** | The spec assumed a photo-level moderation lever that the model and admin never grew. `AdImage` is append-only by construction: no service, no admin action, no FSM step owns single-image removal. |
| **Recommendation** | Add one owner for single-photo removal and wire it to both audiences: a `remove_ad_image(ad_image, actor)` service in the media layer that deletes the row and, per the MEDIA-001 decision, either frees the bytes (exclusive keys) or decrements the count; a moderator `AdImageAdmin.action_remove` (requires a reason string, writes a `ModeratorActionLog` entry so the action is auditable like every other moderation action); and a bot callback that lets the seller drop a photo by position in the photos step. If photo-level moderation is deliberately deferred, correct `technical-specification.md:76` to say the only lever is the whole-ad lifecycle — and correct `edit.py:154`/`technical-specification.md:154` ("Price/photo edits publish immediately"), which currently describes a feature that does not exist. |
| **Effort** | M |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-862 (Missing Authorization) — closest fit for a control the spec grants but the code omits |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | MEDIA-001, AUT-* (phase 15 owns admin RBAC scope) |

**Evidence — `src/backend/apps/ads/admin.py:188-198`** *(supports: "the admin can neither delete nor edit a photo")*:
```python
    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_view_permission(self, request, obj=None) -> bool:
        return request.user.is_staff or request.user.is_superuser

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
```

**Evidence — `docs/01-spec/technical-specification.md:76`** *(supports: "the spec promises a moderator photo-removal lever")*:
```markdown
- Phase-1 moderation is **text-only** (US-A10). Bad photos removed manually by moderator (incl. account ban).
```

**Evidence — `src/backend/apps/ads/views/edit.py:160-171`** *(supports: "the seller edit form has no photo input")*:
```python
            passed, errors = submit_ad(
                SubmitAdInput(
                    ad_id=ad_id,
                    title_ru=dto.title,
                    desc_ru=dto.description,
                    category_id=ad.category_id,
                    city_id=ad.city_id,
                    price_amount=dto.price_amount,
                    price_currency=price_currency_value,
                    photos=[],
                    user_id=ad.user_id,
                    listing_condition_id=ad.listing_condition_id,
                )
            )
```

---

#### MEDIA-006: [MEDIUM] — `/media/` is unrated and the nginx script-execution block documented in the spec does not exist

| Field | Value |
|---|---|
| **ID** | MEDIA-006 |
| **Title** | `/media/` is unrated and the nginx script-execution block documented in the spec does not exist |
| **Severity** | MEDIUM |
| **Category** | Security hardening / Spec deviation |
| **File(s)** | `docker/nginx/nginx.conf:81-87`, `docker/nginx/nginx.dev.conf:82-88`, `docs/01-spec/architecture-structure.md:218` |
| **Status** | Open |
| **Problem** | `architecture-structure.md:218` documents `/media/` security as: "nginx blocks script execution (`location ~* /media/.*\.(php|py|cgi|pl|sh)$ { deny all; return 403; }`); `X-Content-Type-Options: nosniff`; whitelist `image/jpeg`…". Two of those three are present (the `nosniff` header and the `image/jpeg` whitelist on `/protected-media/`); the script-execution block is absent from **both** nginx configs — a grep for `deny all` across `docker/nginx/` returns only the `/metrics` location. Separately, `location /media/` declares no `limit_req` zone, unlike `/login/`, `/search/`, `/moderation/` and `location /`; and `media_gate` has no application-level limiter. Every published photo request therefore reaches Django and PostgreSQL at unlimited rate. |
| **Impact** | No direct exploit today (media is proxied to Django, and `/protected-media/` is `internal` with a MIME whitelist, so there is no execution path). The real cost is the false assurance: a reader of the architecture doc believes a documented control exists, and the missing rate limit means a single client can pull the full image corpus at origin bandwidth and drive unbounded `AdImage` lookups (`media_gate` issues two `EXISTS` queries per request). That is also the cheapest lever for discovering keys, since the gate's 403/404 responses are a perfect oracle. |
| **Root Cause** | The doc was written as a design intent and never diffed against the shipped config; nginx hardening was implemented piecemeal (the `protected-media` block) without a matching pass on the client-facing `/media/` block. |
| **Recommendation** | Two small, independent changes. (1) Add the documented block verbatim to both `nginx.conf` and `nginx.dev.conf` — it costs one `location` and makes the doc true. (2) Add `limit_req zone=browse_limit burst=40 nodelay;` to `location /media/`, matching `location /`. Then either correct the doc's parenthetical or keep it — the point is that the two must agree. A `docker compose config`-style check that greps for the documented locations would prevent the drift recurring. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-770 (Allocation of Resources Without Limits or Throttling) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | MEDIA-009, PERF-* (phase 13) |

**Evidence — `docker/nginx/nginx.conf:80-87`** *(supports: "`/media/` has no `limit_req` and no extension restriction")*:
```nginx
        # Media files proxied to Django for per-request access control
        location /media/ {
            proxy_pass http://web:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
```

**Evidence — grep `deny all|\.php|\.cgi|location ~` over `docker/nginx/`** *(supports: "the documented script-execution block does not exist in either config")*:
```text
C:\py_dev\mko_bazuna\docker\nginx\nginx.conf
  160:        location = /metrics {
  161:            allow 127.0.0.1;
> 162:            deny all;
  163:            proxy_pass http://web:8000;
  164:            proxy_set_header Host $host;
Found 1 matches
```

**Evidence — `docs/01-spec/architecture-structure.md:218`** *(supports: "the doc asserts the block exists")*:
```markdown
- **/media/ security:** nginx blocks script execution (`location ~* /media/.*\.(php|py|cgi|pl|sh)$ { deny all; return 403; }`); `X-Content-Type-Options: nosniff`; whitelist `image/jpeg`, default `application/octet-stream`, `Content-Disposition: inline`; media keys are UUID v4 (unguessable, non-sequential).
```

---

#### MEDIA-007: [MEDIUM] — Staging churn has no disk quota; the 2 h TTL bounds residence time, not the rate

| Field | Value |
|---|---|
| **ID** | MEDIA-007 |
| **Title** | Staging churn has no disk quota; the 2 h TTL bounds residence time, not the rate |
| **Severity** | MEDIUM |
| **Category** | Availability |
| **File(s)** | `src/telegram_bot/handlers/ad_create/photos.py:69-123`, `src/telegram_bot/handlers/ad_create/entry.py:80-100`, `src/backend/apps/media/management/commands/sweep_orphaned_media.py:76-110` |
| **Status** | Open |
| **Problem** | Every accepted photo is written to `MEDIA_ROOT/staging/<uuid>.jpg` and is excluded from the orphan sweep; the only reclamation is `_reclaim_stale_staging`, a 2-hour TTL. The per-seller limiter allows 10 upload *attempts* per 60 s, each of which can consume up to `MAX_PHOTO_BYTES` (2 MB) of Telegram download, and the 5-photo cap is scoped to one FSM flow — starting `/post` again resets it. A seller who repeatedly opens and abandons a draft therefore accumulates roughly 10 × 2 MB per minute of permanently-unreferenced staging files, none of which is reclaimed for two hours. There is no per-seller byte budget, no global staging-directory size check, and no alert on either. |
| **Impact** | A single scripted account can fill the `media_volume` shared with nginx and the web/bot containers. Because the volume backs `/protected-media/`, a full disk stops photo serving for the whole site, not just for the abusive seller. The 2-hour TTL caps steady-state exposure at roughly 2.4 GB per abusive account, so this is a slow-burn resource-exhaustion vector rather than an instant outage. |
| **Root Cause** | The staging directory was given a *time*-based reclamation policy but no *space*-based one, and the only admission control (rate limit + per-flow count) is measured in events rather than bytes. |
| **Recommendation** | Add a space-based guard next to the existing time-based one: in `process_photos`, reject the upload (with a translated message) when the staging directory exceeds a configurable byte budget, and/or delete the seller's own staging files when their FSM is reset by a new `/post`. Keep the TTL — it is correct for genuine abandonment — but make it the backstop rather than the only control. Add a metric on `staging_bytes` so ops can alert before the volume fills. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-400 (Uncontrolled Resource Consumption) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | OPS-* (phase 12 owns volume alerting) |

**Evidence — `src/backend/apps/media/management/commands/sweep_orphaned_media.py:36-38, 76-110`** *(supports: "staging is reclaimed by age only")*:
```python
# Abandoned in-flight uploads older than this are reclaimed by the sweep.
# 2 hours — safely beyond the 30-minute DRAFT retention (sweep_drafts.py).
_STAGING_TTL_SECONDS = 2 * 60 * 60
...
    for dirpath, _dirnames, filenames in os.walk(staging_root):
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                if now - os.path.getmtime(path) >= ttl_seconds:
                    os.remove(path)
```

**Evidence — `src/telegram_bot/handlers/ad_create/photos.py:69-82`** *(supports: "the per-flow count and the per-minute rate are the only admission controls")*:
```python
    if len(photos) >= 5:
        await message.answer(
            _("You already have {count} photos. You can upload at most 5 photos.").format(
                count=len(photos)
            )
        )
        return

    # Enforce per-seller upload burst limit (anti-abuse).
    user_id = data.get("user_id")
    if user_id is not None and not await check_upload_rate_limit(user_id):
        await message.answer(_("Uploading too fast, please wait a moment."))
        return
```

#### MEDIA-008: [MEDIUM] — Seed pipeline records thumbnail keys that were never written, and `seed/` is exempt from the orphan sweep

| Field | Value |
|---|---|
| **ID** | MEDIA-008 |
| **Title** | Seed pipeline records thumbnail keys that were never written, and `seed/` is exempt from the orphan sweep |
| **Severity** | MEDIUM |
| **Category** | Data integrity |
| **File(s)** | `src/backend/apps/seed/generators/images.py:304-316`, `:175-186`, `src/backend/apps/media/management/commands/sweep_orphaned_media.py:33-34, 64-66` |
| **Status** | Open |
| **Problem** | `ImageGenerator._preprocess_one` always rewrites the original, then checks only `<stem>-small.jpg`: if that one file exists it returns `True` immediately without touching medium or large, and the `except FileExistsError` at `:313-314` also returns `True` after merely logging. `generate()` then writes `thumbnail_small/medium/large` keys into the `AdImage` rows unconditionally, via `_thumbnail_key`, regardless of which files actually exist. The key scheme is therefore asserted rather than observed. Because `_walk_media_files` skips `seed/` entirely and `backfill_thumbnails` hits the same `O_EXCL` guard described in MEDIA-004, a missing seed variant is not repairable by either automated path. |
| **Impact** | Dev/demo environments (and any environment that runs `seed`, which `technical-specification.md:217` scopes to development only) can end up with ads whose `thumbnail_small/medium/large_url` point at missing files. Templates fall back to `|default:image.image_url` in the listing and detail galleries, so the visible symptom is oversized originals and a broken layout rather than a hard error — easy to miss, and it disappears only by manually deleting `-small.jpg` and re-running. |
| **Root Cause** | The generator infers file existence from the DB key string instead of from the `ThumbnailService` return value it already receives, and its cache check inspects one of the three outputs it is caching. |
| **Recommendation** | Have `_preprocess_one` return the actual generated keys (or a truthful `None`) and build the `AdImage` thumbnail fields from that, so the DB can never claim a file that was not written. Extend the cache check to all three variants — or drop it and rely on `ThumbnailService`'s `O_EXCL` (which already handles "already generated" correctly, by the design in MEDIA-008's fix). Reuse the stale-file-vs-race guard from MEDIA-004 so a half-written seed variant is regenerated instead of skipped. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-459 (Incomplete Cleanup) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | MEDIA-004, MEDIA-003 |

**Evidence — `src/backend/apps/seed/generators/images.py:300-316`** *(supports: "the cache check inspects one of three variants and both paths return success")*:
```python
        # Write original image
        with open(original_path, "wb") as f:
            f.write(img_bytes)

        # Generate thumbnails
        thumb_small = os.path.join(
            seed_dir, f"{os.path.splitext(filename)[0]}-small.jpg"
        )
        if os.path.exists(thumb_small):
            return True

        try:
            thumbnail_service.generate_thumbnails(img_bytes, filename)
        except FileExistsError:
            logger.warning("Thumbnails already exist for %s, skipping", filename)

        return True
```

**Evidence — `src/backend/apps/seed/generators/images.py:178-186`** *(supports: "the row records all three keys unconditionally")*:
```python
                ad_img = AdImage(
                    ad=ad,
                    image=key,
                    position=position,
                    thumbnail_small=self._thumbnail_key(key, "small"),
                    thumbnail_medium=self._thumbnail_key(key, "medium"),
                    thumbnail_large=self._thumbnail_key(key, "large"),
                )
                ad_images.append(ad_img)
```

**Evidence — `src/backend/apps/media/management/commands/sweep_orphaned_media.py:64-66`** *(supports: "`seed/` is excluded from reconciliation, so a leftover there is never reclaimed")*:
```python
        # Skip seed directory (and any subdir starting with seed/)
        if rel_dir == _SEED_SUBDIR or rel_dir.startswith(f"{_SEED_SUBDIR}/"):
            continue
```

---

#### MEDIA-009: [MEDIUM] — No documented storage-key ownership model; the DB docs assert a key structure the code does not produce

| Field | Value |
|---|---|
| **ID** | MEDIA-009 |
| **Title** | No documented storage-key ownership model; the DB docs assert a key structure the code does not produce |
| **Severity** | MEDIUM |
| **Category** | Documentation |
| **File(s)** | `docs/02-database/db-schema.md:320-321`, `docs/02-database/db-retention.md:102`, `docs/01-spec/architecture-structure.md:218`, `src/backend/apps/media/services/filesystem.py:174-176` |
| **Status** | Open |
| **Problem** | Three documents describe the storage key differently, and none of them states who owns the bytes. `db-schema.md:320-321` says the key is "ad-scoped + UUID v4" and contains "only ad_id + UUID v4"; `generate_storage_key` emits `f"{uuid.uuid4()}.jpg"` — **no ad_id at all**. `architecture-structure.md:218` says "media keys are UUID v4 (unguessable, non-sequential)"; seeded keys are `seed/<semantic-filename>.jpg` (e.g. `seed/apartments_04.jpg`), which is neither UUID nor unguessable. Most importantly, `db-retention.md:102` and `technical-specification.md:88` both promise that erasure "removes physical ad-image files", an assertion that only holds if each key has exactly one owner — the assumption MEDIA-001 shows is false. A grep for `refcount` / `reference count` / `same storage key` / `ownership` across `docs/` returns nothing. |
| **Impact** | The documentation is the specification the erasure and retention reviews rely on, and it is wrong in the one respect that matters most (exclusivity). A reviewer confirming MEDIA-001's fix by reading the docs would be misled; an operator debugging a missing file would look for an ad-scoped key format that has never existed. This is a `[DOC-UPDATE]`, not a code defect: the code should keep the current key scheme (dropping the ad_id would *reduce* unguessability, which is the actual security goal) and the docs should be corrected to match. |
| **Root Cause** | `AdImage.storage_keys()` and the `pre_delete` signal encode an ownership invariant that was never written down, so the invariant survived only as an undocumented assumption in three places that each restate it slightly differently. |
| **Recommendation** | Update `db-schema.md:320-321` to state the real scheme (`<uuid4>.jpg` for bot uploads, `staging/<uuid4>.jpg` in flight, `seed/<filename>.jpg` for seed data; no ad_id, by design, to preserve URL unguessability) and state the ownership rule in one sentence — "a storage key is owned by exactly one `AdImage` row; `seed/` keys are the documented exception" — until MEDIA-001 changes it. Add the same rule to `architecture-structure.md:218` next to the `/media/` security bullet, and qualify `db-retention.md:102` / `technical-specification.md:88` with a pointer to that rule. Fix the "keys are UUID v4" claim to note the `seed/` exception. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | MEDIA-001, MEDIA-006 |

**Evidence — `src/backend/apps/media/services/filesystem.py:174-176`** *(supports: "the generated key contains no ad_id")*:
```python
def generate_storage_key() -> str:
    """Generate a UUID v4 storage key for anonymity."""
    return f"{uuid.uuid4()}.jpg"
```

**Evidence — `docs/02-database/db-schema.md:320-321`** *(supports: "the doc claims an ad-scoped key")*:
```markdown
image (VARCHAR / storage key)        # served URL/key (our storage). Phase 1: local MEDIA_ROOT via FileSystemStorage.
                                    #   Key contains NO user_id/telegram_id/username — only ad_id + UUID v4 (zone R6: URL anonymity)
```

**Evidence — grep `refcount|reference count|shared key|exclusive owner|same storage key|reuses the source` over `docs/`** *(supports: "no ownership model is documented anywhere")*:
```text
No files found
```

### LOW

#### MEDIA-010: [LOW] — `MediaDeletionError` escalation table is write-only — no reader, no retention, no admin

| Field | Value |
|---|---|
| **ID** | MEDIA-010 |
| **Title** | `MediaDeletionError` escalation table is write-only — no reader, no retention, no admin |
| **Severity** | LOW |
| **Category** | Observability |
| **File(s)** | `src/backend/apps/media/models.py:11-56`, `src/backend/apps/media/services/filesystem.py:233-250` |
| **Status** | Open |
| **Problem** | `models.py:5` says the model exists "enabling operational escalation (ME-003)", and `_record_deletion_error` writes a row whenever `delete_photo` exhausts its three retries. There is no `@admin.register(MediaDeletionError)` anywhere in the app, no management command that reads or prunes the table, no `expires`/retention policy, and no metric or alert wired to it. A persistent condition — a read-only `MEDIA_ROOT`, a `chattr +i` file, an immutable mount — writes one row per key per sweep run, forever. |
| **Impact** | The designed escalation path cannot actually be used: an operator has to know to `psql` the table, and the table itself becomes an unbounded growth source that masks the signal it exists to raise. The underlying problem is still visible (`logger.error("Failed to delete photo %s after %s attempts"…)` at `filesystem.py:222-228`), so nothing is silently lost — which is why this is LOW, not MEDIUM. |
| **Root Cause** | The write side was built and tested; the read side was deferred and never scheduled. |
| **Recommendation** | Add an `admin.py` to the media app registering `MediaDeletionError` with `created_at`/`error_type` filters and a `readonly_fields`-only change form, and add a `sweep_media_deletion_errors --older-than N` command to the existing hourly command list (reusing `AdvisoryLockId.SWEEP_ORPHANED_MEDIA` is not appropriate — add a new `AdvisoryLockId` member per the StrEnum rule). An alert on `MediaDeletionError.objects.filter(created_at__gt=now()-1h)` is a one-line addition to whatever alerting phase 12 lands. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-778 (Insufficient Logging) |
| **Likelihood** | LOW |

| Field | Value |
|---|---|
| **Related Findings** | OPS-* (phase 12) |

**Evidence — `src/backend/apps/media/models.py:1-6`** *(supports: "the stated purpose is operational escalation")*:
```python
"""
Media models for Mko Bazuna.

``MediaDeletionError`` records filesystem deletion failures that exhausted
all retries in ``delete_photo``, enabling operational escalation (ME-003).
"""
```

**Evidence — grep `MediaDeletionError` across `src/` (excluding tests)** *(supports: "there is no admin registration, reader, retention job or documentation — only the write")*:
```text
src/backend/apps/media/models.py:11                              class MediaDeletionError(models.Model):
src/backend/apps/media/models.py:56                              return f"MediaDeletionError: {self.storage_key} ..."
src/backend/apps/media/services/filesystem.py:241                from apps.media.models import MediaDeletionError
src/backend/apps/media/services/filesystem.py:243                MediaDeletionError.objects.create(
src/backend/apps/media/services/filesystem.py:250                logger.exception("Failed to persist MediaDeletionError for %s", ...)
src/backend/apps/media/migrations/0001_initial.py:13             name="MediaDeletionError",
(0 matches in docs/, 0 matches in docker/, no @admin.register anywhere)
```

---

#### MEDIA-011: [LOW] — Stored originals are re-encoded at Pillow's default quality 75 with no documented rationale

| Field | Value |
|---|---|
| **ID** | MEDIA-011 |
| **Title** | Stored originals are re-encoded at Pillow's default quality 75 with no documented rationale |
| **Severity** | LOW |
| **Category** | Maintainability / Documentation |
| **File(s)** | `src/backend/apps/media/services/filesystem.py:253-272`, `docs/01-spec/technical-specification.md:77` |
| **Status** | Open |
| **Problem** | `strip_photo_exif` saves with `optimize=True` and no `quality` argument, so Pillow's default (75) applies — every seller photo is re-compressed a second time on top of the compression Telegram already applied, at a quality the code never chose out loud. `ThumbnailService` is explicit (`QUALITY = 85`) but the original writer is not. Separately, `technical-specification.md:77` states "No server-side photo optimization in phase 1 — accept Telegram-compressed images, store in our storage, serve as-is", which the shipped pipeline (full re-encode + three derivatives) directly contradicts. |
| **Impact** | Two small, non-urgent costs. Quality: photos are stored at a lower effective quality than the seller uploaded, with no way to change it without a code edit, and no test or doc recording the intent — so a future "optimisation pass" has nothing to reason from. Documentation: a reader of the spec would conclude no re-encoding happens and could wrongly conclude the EXIF strip does not either. |
| **Root Cause** | The re-encode began as a metadata-stripping step and inherited Pillow's defaults; the spec was written when that was still true and was never revisited. |
| **Recommendation** | Keep the re-encode (stripping EXIF/ICC is required and verified working — R-06/R-07), and make the choice explicit: add a named `STORED_JPEG_QUALITY` constant with a short comment next to the save call so the number is reviewable and tunable. Then correct `technical-specification.md:77` (and the neighbouring "phase 1 serves full-size compressed photos" at `:79`) to describe the actual pipeline: EXIF/ICC stripped, re-encoded at the named quality, three derivative sizes generated. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | MEDIA-009 |

**Evidence — `src/backend/apps/media/services/filesystem.py:266-272`** *(supports: "no `quality` argument — Pillow's default 75 applies")*:
```python
    img = Image.open(io.BytesIO(photo_bytes))
    img = ImageOps.exif_transpose(img)
    img.info.pop("exif", None)
    img.info.pop("icc_profile", None)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", optimize=True, comment=b"", exif=b"")
    return buf.getvalue()
```

**Evidence — `docs/01-spec/technical-specification.md:77`** *(supports: "the spec says the image is stored as-is")*:
```markdown
- **No server-side photo optimization in phase 1** — accept Telegram-compressed images, store in our storage (decision E-storage), serve as-is.
```

**Evidence — probe R-3, byte-level before/after** *(supports: "the file is genuinely re-encoded, and the result is clean")*:
```text
  incoming bytes=1811 exif_app1_present=True comment_present=False gps_tag=110
  stripped bytes=658 exif_app1_present=False exif_tag_count=0 make_bytes_present=False comment_bytes_present=False
[R3.EXIF] strip_photo_exif removes EXIF: PASS tag_count=0
[R3.XMP] XMP packet removed by strip_photo_exif: PASS
```

---

## Cross-Finding Analysis

- **Merge candidates:** MEDIA-003, MEDIA-004 and MEDIA-008 all reduce to the same missing filesystem invariant — *a media file is either fully materialised and referenced, or it does not exist*. MEDIA-003 breaks it across the staging→permanent boundary, MEDIA-004 across the three-variant write, MEDIA-008 across the seed generator. They are filed separately because the triggers, owners and fixes are in three different modules, but a single fix ("make every media write atomic and keep unreferenced material inside a protected namespace until its row commits") would address all three. Recommend the validator check for a merge.
- **Conflicting evidence:** None. Two apparent conflicts resolved in favour of the code: (a) the spec's "serve as-is" (MEDIA-011) is stale — the re-encode is the safer behaviour and the doc should change, not the code; (b) phase 01's ENT-009 and phase 03's DB-005 both describe the `submit_ad` / `sweep_orphaned_media` interaction from the locking and DB-snapshot sides. This phase files only the filesystem *consequence* (the file is destroyed and cannot be regenerated) and does not restate the locking analysis.
- **Dependency chains:**
  1. **MEDIA-001 → MEDIA-002.** The dedup fix (002) can create *more* shared-key situations or fewer, depending on whether the chosen direction is "copy the file" or "reference the blob". Land the ownership decision in 001 first, or the 002 fix may be written against a model that is about to change.
  2. **MEDIA-001 → MEDIA-009.** The ownership rule can only be documented once it is decided; the docs currently assert the opposite.
  3. **MEDIA-004 → MEDIA-008.** The seed generator needs the same stale-file guard; fixing 008 before 004 would re-introduce the same class of defect.
  4. **MEDIA-001 → MEDIA-005.** A moderator/seller photo-removal action must decrement a refcount or free an exclusive key; it cannot be written safely before 001 settles the model.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | MEDIA-001 | CRITICAL | M | P0 | Define and enforce storage-key ownership (exclusive key, or a refcounted blob owner) in the media layer; make `pre_delete` reference-aware. |
| 2 | MEDIA-002 | HIGH | S | P0 | Scope `create_or_skip` dedup to the target ad; make the skip observable to `submit_ad` and reclaim the unused files. |
| 3 | MEDIA-003 | HIGH | S | P0 | Keep promoted files in a protected namespace (or add an mtime grace window) until the `AdImage` row commits. |
| 4 | MEDIA-004 | HIGH | S | P1 | Make thumbnail writes atomic (temp + `os.replace`); teach the backfill to distinguish a stale file from a real race. |
| 5 | MEDIA-009 | MEDIUM | S | P1 | Correct `db-schema.md` / `architecture-structure.md` to the real key scheme; state the ownership rule explicitly. |
| 6 | MEDIA-005 | MEDIUM | M | P1 | Add a single-photo removal service + moderator action + bot affordance, or correct the spec. |
| 7 | MEDIA-007 | MEDIUM | S | P1 | Add a staging byte budget and a `staging_bytes` metric alongside the existing TTL. |
| 8 | MEDIA-006 | MEDIUM | S | P2 | Add the documented nginx script block and a `limit_req` zone to `location /media/`. |
| 9 | MEDIA-008 | MEDIUM | S | P2 | Build seed `AdImage` thumbnail fields from the real `ThumbnailService` return value. |
| 10 | MEDIA-010 | LOW | S | P2 | Register `MediaDeletionError` in the admin and add a retention sweep + alert. |
| 11 | MEDIA-011 | LOW | S | P2 | Name the stored-original JPEG quality; correct the "no server-side optimization" spec line. |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| MEDIA-001 | High — the fix changes when bytes are freed; a wrong refcount either leaks files forever or re-creates today's data loss | No — existing rows that share a key must be migrated or the first delete after deploy reproduces the bug | No test exists for a key referenced by two `AdImage` rows. Need: copy→delete-source leaves the copy's file intact; a store↔DB diff that fails on any dangling row; the same for `create_draft_ad` after `copy_ad` (the R-13 reproduction). |
| MEDIA-002 | Med — a seller who has reposted the same photo now gets a row where they previously got none; that is a behaviour change, and existing photo-less ads stay photo-less | Yes for existing data; new behaviour is strictly more correct | `test_ad_image_service.py` asserts the current cross-ad dedup semantics and will need rewriting. Add: identical bytes to two ads ⇒ both ads have one image, zero orphans. |
| MEDIA-003 | Med — narrowing what the sweep deletes means orphans survive one extra cycle; harmless, but disk-use dashboards shift | Yes | `test_sweep_orphaned_media.py` has a genuine-orphan test that must keep passing; add: a file newer than the sweep start is not deleted. |
| MEDIA-004 | Low — only changes behaviour on a failure path that currently loses data | Yes | `test_thumbnails.py` / `test_backfill_thumbnails.py` need a stale-file-vs-race case, and a partial-write case that asserts no partial files remain. |
| MEDIA-009 | Low — docs only | Yes | n/a (documentation) |
| MEDIA-005 | Med — a new delete surface on `AdImage`; must be permission-gated and audited or it becomes an authorization gap (phase 15) | No — new capability | `test_media_security.py` must assert the new path is staff-only and writes a `ModeratorActionLog` row. |
| MEDIA-007 | Low — a new rejection branch in the bot handler; needs a translated message (i18n is part of DoD, gate-enforced by `test_i18n_completeness.py`) | Yes | New i18n strings; the fast gate must pass. |
| MEDIA-006 | Low — pure nginx config; a bad `location` regex would 403 real photos, so verify against a live key before rollout | Yes | No test; verify with `nginx -t` and one real media request in the deployed stack. |
| MEDIA-008 | Low — dev/seed path only | Yes | `test_seed.py::test_media_cleanup` and the `real_images`-marked tests must be re-run with the new assertion. |
| MEDIA-010 | Low — adds an admin read surface and a new hourly command | Yes | New command needs a lock-id entry in `test_sweep_lock_structure.py`. |
| MEDIA-011 | Low — a named constant; changing the value changes stored bytes for new uploads only | Yes | `test_save_photo_exif.py` / `test_thumbnail_integration.py` still pass unchanged. |

## Appendices

### Appendix A — Runtime verification harness

Both probes ran inside the `mko-bazuna-test` image via
`docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm --no-deps --entrypoint "" test python /app/.ai/tmp/audit07_probe{,2}.py`.
Each created a scratch database (`audit07_probe`, `audit07_probe2`) via `psycopg` against the
`postgres` maintenance DB, repointed `settings.DATABASES["default"]["NAME"]` at it, ran
`migrate --run-syncdb`, and used a fresh `tempfile.mkdtemp()` as `MEDIA_ROOT`. Both dropped the
database and removed the temp `MEDIA_ROOT` in a tail block, and both probe scripts were deleted
afterwards. **No file in the repository's `media/` directory and no row in the phantom
`mko_bazuna` database was read for writing, modified or deleted.**

Probe 1 summary (`total=55 pass=53 fail=2`):

```text
R-1  access control        12/12 PASS   (7 statuses, staff, declined, withdrawn, shared key, cache headers)
R-2  path traversal         7/7  PASS   (+ 4/4 assert_storage_key_contained)
R-3  EXIF/metadata         7/7  PASS   (EXIF, GPS, Make, comment, XMP, 3 thumbnails)
R-4  dedup                  0/3  PASS -> MEDIA-002
R-5  copy_ad + pre_delete   3/3  "PASS" (the observed behaviour IS the defect) -> MEDIA-001
R-6  thumbnail atomicity    3/3  "PASS" (the observed behaviour IS the defect) -> MEDIA-004
R-7  sweep vs in-flight     2/3  PASS   (1 FAIL -> MEDIA-003)
R-8  store/DB diff          1/2  PASS   (1 FAIL: 5 dangling rows -> MEDIA-001)
R-9  key randomness         PASS
R-10 upload validation      6/6  PASS
R-11 PII erasure cascade    4/4  PASS
```

Probe 2 summary (`total=8 pass=7 fail=1`; the single FAIL is a probe artifact — it asserted
`MEDIA_ROOT` is a `pathlib.Path`, which the probe itself had replaced with a `str`):

```text
R-12 /post vs shared keys   2/2  "PASS" (the observed behaviour IS the defect) -> MEDIA-001
R-13 DRAFT thumbnail 403    5/5  PASS   (incl. the owning seller's own session)
R-14 shipped seed EXIF      SKIP (see below)
R-15 MEDIA_ROOT type        FAIL (probe artifact, not a finding)
```

### Appendix B — The shipped seed JPEG has no metadata

`media/seed/apartments_04.jpg` could not be inspected inside the container (the test service's
`.:/app` bind mount does not expose that directory on this host), so it was scanned byte-wise on
the host instead. The JPEG segment walk below shows the complete marker list: only `FFE0` (JFIF
APP0), two `FFDB` (DQT), `FFC0` (SOF0) and four `FFC4` (DHT) before `SOS`. No `FFE1` (EXIF or
XMP), no `FFE2` (ICC), no `FFFE` (COM), no `FFED`/`FFE8` (Photoshop/IPTC). This corroborates
`apps/seed/generators/images.py:296-298`, which runs `strip_photo_exif` on the fixture bytes
before writing them to `MEDIA_ROOT/seed/`.

```text
size: 79684
contains 'Exif': False
contains 'xmp': False
contains 'ICC_PROFILE': False
contains 'photoshop': False
  segment FFE0 len=16     (APP0/JFIF)
  segment FFDB len=67     (DQT)
  segment FFDB len=67     (DQT)
  segment FFC0 len=17     (SOF0)
  segment FFC4 len=28     (DHT)
  segment FFC4 len=82     (DHT)
  segment FFC4 len=25     (DHT)
  segment FFC4 len=42     (DHT)
  SOI..SOS scan complete
```

### Appendix C — Quality gates on the media surface

```text
$ uv run ruff check src/backend/apps/media src/backend/apps/ads/views/listings.py \
      src/backend/apps/ads/services/{images,copy_service,submission}.py \
      src/telegram_bot/services/ad_data src/telegram_bot/handlers/ad_create/photos.py
All checks passed!

$ uv run basedpyright src/backend/apps/media src/backend/apps/ads/views/listings.py \
      src/backend/apps/ads/services/{images,copy_service}.py \
      src/telegram_bot/services/ad_data/media.py src/telegram_bot/handlers/ad_create/photos.py
0 errors, 0 warnings, 0 notes

$ pytest src/backend/apps/media src/backend/apps/ads/tests/test_media_security.py \
         src/telegram_bot/tests/test_save_photo_integration.py \
         src/telegram_bot/tests/test_ad_create.py
133 passed
```

### Appendix D — What was not audited, and why

- **The live reverse proxy.** `mko-bazuna-dev-web-1` and `mko-bazuna-dev-bot-1` are crash-looping
  (CFG-006, placeholder `BOT_TOKEN` in `.env.dev`), so no HTTP request was issued through nginx.
  All access-control evidence is from Django's test client with `DEBUG=False`, which exercises
  the real URLconf, middleware and the production `X-Accel-Redirect` branch. Whether nginx
  actually honours the header, applies the `image/jpeg` whitelist and honours `internal` was
  assessed by reading `docker/nginx/nginx.conf` only.
- **`MediaDeletionError` on a real failing filesystem.** The retry-exhaustion path was read, not
  triggered on a real read-only mount.
- **Scale behaviour of the orphan sweep** (`os.walk` over a large `MEDIA_ROOT`, the
  snapshot→walk→unlink window). Phase 03 owns DB-005; the media-owned part is MEDIA-003.
- **`AdImage` authorization** beyond the admin permission flags. Phase 15 owns RBAC.
- **The real `media/` volume** and any production `MEDIA_ROOT` — untouched by design.
- **gitleaks / pre-commit** — not installed on this host; no secret scan was run and none is
  claimed. No secret value was read or quoted; only variable names appear in this report.

