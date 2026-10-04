---
id: media-store-operations
domain: ops
tags:
  - media
  - storage
  - nginx
  - staging
  - thumbnails
  - operations
related:
  - docker-deployment
  - db-retention
  - db-schema
  - architecture-structure
  - seed-workflow
---

## Purpose

Operator-facing description of the ad-photo store in `MEDIA_ROOT`: how files are named, when
their bytes are created and freed, what bounds them, and which commands reconcile the store
against the database. This document is the **operational** view. Two facts have a different
canonical home and are only summarised here, never restated in full:

| Fact | Canonical home |
|------|----------------|
| Storage-key **schema** and the **N ≥ 1 ownership rule** | [`db-schema.md`](../02-database/db-schema.md#ad_images) |
| **Retention windows** for `sweep_orphaned_media` / `purge_media_deletion_errors` | [`db-retention.md`](../02-database/db-retention.md) |
| **nginx** location blocks, zones and headers | [`docker-deployment.md`](docker-deployment.md#nginx-configuration) |

## Main Concepts

### Storage key scheme

Three legitimate key families, all matching `KEY_FORMAT_REGEX` in
`apps/media/services/filesystem.py`:

| Family | Example | Lifetime |
|--------|---------|----------|
| Stored original (plus `-small` / `-medium` / `-large` siblings) | `<uuid4>.jpg` | Bounded by `AdImage` rows |
| In-flight upload | `staging/<uuid4>.jpg` | Bounded by the mtime TTL and the byte budget |
| Generated demo data | `seed/<filename>.jpg` | Bounded by `SeedService._clean()` |

**There is no `ad_id` in a key, by design** (zone R6, URL anonymity): an ad-scoped key would
expose the ad id in a served URL. Keys are `uuid4()`, therefore unguessable and non-sequential
— and therefore **unattributable to a seller**, which is the reason the staging budget below
is global.

A key may be referenced by **N ≥ 1** `AdImage` rows (`copy_ad` points a copy at the source
ad's keys instead of duplicating files), so bytes are freed only when the **last** referencing
row goes away. The single still-referenced predicate is
`apps.media.services.references.unreferenced_keys` — one combined query over all four key
columns — evaluated inside the `transaction.on_commit` closure registered by
`apps.media.signals.delete_adimage_files_on_delete`. Two residuals are accepted and
undocumented-as-fixed: in a multi-row cascade a shared key is passed to `delete_photo` once
per departing row, and a concurrent insert between the reference query and the `unlink` is
not closed.

### Duplicate detection is scoped to the ad, not the seller

`AdImageService.create_or_skip` matches on `(ad, sha256)`. The same bytes attached to a
**different** ad — including another ad by the same seller — are a distinct upload and get
their own row and their own key.

A skipped upload has already written **1 to 4** staged files by the time the skip is detected:
the original at `staging/<uuid>.jpg` plus up to three `-small` / `-medium` / `-large`
siblings (the bare `except` in the bot's thumbnail loop nulls all three on failure and
appends none). Those bytes are reclaimed **post-commit** through
`filesystem.reclaim_staged_keys`, and the keys are pruned from the list handed to
`promote_media_files` by in-place slice assignment — so a skipped upload is never promoted to
a permanent orphan. A reclaim failure leaves the file in `staging/` for the TTL rather than
promoting it.

### Staging byte budget

`MEDIA_STAGING_BYTE_BUDGET` (default **2 GiB**) caps bytes held in `MEDIA_ROOT/staging/`. The
check runs in the bot photo handler **before** `save_photo`, so a refused upload writes zero
bytes and answers "Storage is temporarily full. Please try again later."

- **The budget is global, not per-seller.** Staging keys are `uuid4()` and carry no owner
  attribute, so per-seller attribution is infeasible. **One seller can exhaust the shared
  budget** for everyone; the per-seller bot rate limit (10 uploads / 60 s,
  `check_upload_rate_limit`) does not bound this.
- The total comes from `staging_bytes_used()`, a top-level `os.scandir` of `staging/` that
  never recurses and never `os.walk`s — O(entries in `staging/`), not O(store size). Entries
  that vanish mid-scan are skipped rather than failing the upload.
- **No Prometheus gauge ships.** `PROMETHEUS_MULTIPROC_DIR` is set only on the `web` service,
  so a gauge written from the bot-side path is structurally unexportable. Watch the disk and
  `staging/` size directly.
- `staging/` is the **sole** suppression in the orphan sweep; its files are reclaimed by mtime
  TTL (`_STAGING_TTL_SECONDS`, 2 h), which is also what bounds the promote-before-commit gap.

### Stored bytes are re-encoded, and the store is mixed-quality by design

The served photo is **not** the raw Telegram upload. Every stored original is re-encoded at
`apps.media.services.filesystem.STORED_JPEG_QUALITY` (**75**) to strip EXIF/ICC/comment;
thumbnails are derived at `ThumbnailService.QUALITY` (**85**), LANCZOS, progressive JPEG, at
240x180 / 640x480 / 1280x960. The two numbers differ deliberately and the modules share no
import edge, so each declares its own. **No re-derivation is scheduled**: bytes already in the
store keep the quality they were written with.

### Thumbnail publication is atomic per file

`ThumbnailService.generate_thumbnails` writes a temp file **in the destination directory** and
then publishes it:

| `WriteMode` | Mechanism | Used by |
|-------------|-----------|---------|
| `CREATE_ONLY` (default) | `os.link` — refuses to overwrite | normal generation |
| `REPLACE` | `os.replace` | repair callers, incl. the seed generator |

Consequences an operator should know:

- **The temp file mode is `0o666` subject to umask — deliberately, and never
  `tempfile.mkstemp`.** `mkstemp` creates `0600`; nginx serves `/media/` as a different uid
  from the app, so a `0600` published file would **403 every image on the site**. Observed mode
  in this project's container is `0755`. Diagnose with `ls -l $MEDIA_ROOT/*.jpg`: a batch of
  `-rw-------` files needs a mode fix, not a re-upload.
- Temp names carry a leading dot and a `.tmp` suffix, so a leaked temp can never match
  `KEY_FORMAT_REGEX` (which requires `.jpg`) and can never be mistaken for a real key; it is
  unreferenced and reclaimed by the hourly orphan sweep.
- **Crash durability is not claimed.** There is no `fsync` of the temp file or of the
  directory, so a host crash immediately after publication can in principle leave a
  zero-length or absent file. `sweep_orphaned_media --check` is the detector.
- `backfill_thumbnails` distinguishes a **stale leftover** (thumbnail column `NULL` while the
  file is present → `REPLACE`) from a genuine concurrent race (`CREATE_ONLY`, which surfaces
  `FileExistsError` instead of silently overwriting).

### Reconciling the store against the database

```bash
# Read-only report; exits non-zero (CommandError) on any mismatch.
# Not the default — the bare invocation is the destructive orphan sweep.
python src/backend/manage.py sweep_orphaned_media --check

# Mandatory dry run before the irreversible diagnostic-table purge.
python src/backend/manage.py purge_media_deletion_errors --dry-run
```

`sweep_orphaned_media --check` reports both directions — a **dangling row** (a referenced key
whose file is absent) and **orphan files** on disk — includes `seed/` in its scope (unlike the
destructive walk) and probes each referenced key **verbatim**; `staging/` is the only
suppression. The destructive sweep's counter now increments only for files it actually
removed, so a retry-exhausted or already-absent file is not reported as deleted. Full
semantics: [`db-retention.md`](../02-database/db-retention.md#sweep_orphaned_media---check-07-media-012).

### Moderator single-photo removal

`apps.ads.services.ad_image_removal.remove_ad_image`, exposed as the staff-only, audited
`AdImageAdmin.action_remove_photo` action. It deletes the **`AdImage` row** and lets the
reference check above free the bytes — it never calls `delete_photo`, so there is exactly one
byte-freeing route. The audit row uses `ModeratorActionType.OTHER` with a canned reason (never
free text from the request), and the row is read under `select_for_update()` rather than a
new process-wide advisory lock: a single-row delete needs a row lock, and no new lock id is
allocated for it. Seller-side photo editing does **not** exist in phase 1.

### Seed asserts what it wrote

`ImageGenerator._preprocess_one` returns a thumbnail mapping only when **every** variant has a
file behind it on disk. When all three already exist it returns without re-encoding (the cache
check covers all variants, not just the first); otherwise it publishes with
`WriteMode.REPLACE`, because `CREATE_ONLY` aborts on the first present size and never reaches
a missing one. A failed publish propagates instead of being swallowed — the seed can no longer
report success for a photo whose thumbnails were never written.

## Related Documentation

- [`db-retention.md`](../02-database/db-retention.md) — retention windows and the purge/sweep semantics
- [`db-schema.md`](../02-database/db-schema.md#ad_images) — `ad_images` columns, key schema, ownership rule
- [`docker-deployment.md`](docker-deployment.md#media-security) — nginx `/media/` blocks, rate limits, env vars
- [`architecture-structure.md`](../01-spec/architecture-structure.md) — topology, scheduler, advisory-lock allocation
- [`seed-workflow.md`](seed-workflow.md) — fixture download and the seed photo pipeline
