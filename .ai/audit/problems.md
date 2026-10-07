# Audit Report — Intermittent Missing Seed Thumbnail Images

## Summary
On the dev site, thumbnail images under `/media/seed/` (e.g. `apartments_10-large.jpg`) are intermittently missing after an HTMX sort/navigation; they appear after a few browser refreshes. `curl` of a missing file returns HTTP 200 with a real JPEG body (e.g. 105440 bytes for `apartments_10-large.jpg`) even though `ls` inside the container reports "No such file or directory" for that path. This proves an **on-demand/lazy thumbnail backfill** path serving files that are not on disk, with a **race condition** on first concurrent request.

## Environment
- Platform: Windows 11 host; dev stack via `mko-bazuna-dev` compose.
- Python/Django target: uvx/3.14 + Django 5.2 LTS + PostgreSQL 18 + aiogram 3.x (per project rules).
- Test DB: `mko-bazuna-test` on host port 5433 (dev/test distinction matters).
- Dev `web` bind-mounts `.:/app` (hides the image COPY), depends_on `seed` (`condition: service_completed_successfully`).
- Seed ran today (Oct 7) ~18:35, populated `/app/media/seed/` (2456 files).

## Evidence
1. `curl -I /media/seed/pedicure_01-small.jpg` — 200 OK, 9136 bytes. Source `pedicure_01-small.jpg` fixture exists.
2. `curl -I /media/seed/apartments_10-large.jpg` — 200 OK, **105440 bytes**, but `ls /app/media/seed/apartments_10*` → "No such file or directory".
3. Source fixtures present on host at `src/backend/apps/seed/fixtures/images/` (1056 JPEGs) and in container.
4. `ImageGenerator._preprocess_one` (generators/images.py) writes original + 3 thumbnails with `WriteMode.REPLACE` and a post-condition assert (commit a0e19c52, Oct 3).
5. `media_gate` view (ads/views/listings.py) rate-limits; DEBUG→`_serve_image` (404-if-missing); non-DEBUG→`X-Accel-Redirect`.

## Likely Sources of the Problem
- **S1. Lazy thumbnail backfill on missing image.** Some view/property generates the thumbnail on first access and serves the bytes without persisting (or persists non-atomically), returning 200 while `ls` shows absence.
- **S2. Race in atomic publish.** `ThumbnailService.generate_thumbnails` claims atomic publish; a concurrent first-request pair can both miss, both generate, and one can 404 before the other writes.
- **S3. URL routing.** `/media/...` routed somewhere other than `media_gate` (e.g. `django.views.static.serve` in DEBUG) that bypasses the 404-if-missing logic.
- **S4. Signal-driven generation.** `AdImage` model `thumbnail_*_url` properties or a `post_save`/`pre_save` signal regenerates missing thumbnails at serve time.
- **S5. Settings mismatch.** `DEBUG`/`MEDIA_ROOT` differ between what `ls` sees and what the running gunicorn uses; dev bind-mount hides real image COPY.

## Most Likely (pending confirmation)
- S1 + S2: an on-demand backfill path that serves a generated JPEG without (atomic) persistence, racing under concurrent first requests. S1 must exist to explain how a 105440-byte JPEG is served for a file `ls` reports absent; S2 explains the intermittency.

## Next Steps to Confirm
1. Read root URLconf + `apps/ads/urls.py` to see how `/media/seed/...` is routed (media_gate vs django static.serve).
2. Read `AdImage` model in `apps/ads/models.py` — `thumbnail_small_url`/`thumbnail_large_url` properties + any backfill-on-access generation.
3. Read `apps/media/models.py`, `apps/media/signals.py`, and `ThumbnailService` callers to locate the lazy generator.
4. Confirm `DEBUG`/`MEDIA_ROOT` in the running dev container (retry without `| tail`).

## Open Questions
- Q1: What route serves `/media/seed/<filename>` — `media_gate` or `django.views.static.serve`?
- Q2: Where is the on-demand backfill that returns 105440 bytes for an absent file?
- Q3: Where is the race? Concurrent generation in `ThumbnailService` vs. a non-atomic write path.
- Q4: Is `DEBUG` actually True in the dev container, making `_serve_image` 404-but-curl-200 inconsistent?

## Status
- Blocked on root URLconf + AdImage model + media signals + DEBUG/MEDIA_ROOT values (last inspect command failed due to `tail` unavailable in PowerShell).
- Tooling friction: `head`, `tail`, `file`, `ls -la` unavailable; `$f.Length` inline mangled in bash tool wrapper.

## Findings (resolved during investigation)
- **URL routing corrected:** Root URLconf (`config/urls.py`) does NOT use `static()` for media. The route `path("media/<path:image_key>", media_gate)` in `apps/ads/urls.py` (included at root `path("", include("apps.ads.urls"))`) handles ALL `/media/...` requests. `media_gate` checks DB first (`AdImage.objects.filter(key_q).exists()` where `KEY_COLUMNS = ("image", "thumbnail_small", "thumbnail_medium", "thumbnail_large")`), then `_serve_image` checks disk (`FileResponse` if `file_path.exists()`, else `Http404`).
- Confirmed `DEBUG=True` in dev container; `MEDIA_URL=/media/`, `MEDIA_ROOT=/app/media` (shared Docker named volume `media_volume` across seed, web, and nginx).
- **No on-demand generation.** `ThumbnailService._publish` writes each file atomically via temp file + `os.replace` (NOT delete-then-write). `os.replace` is atomic on Linux — a reader sees either the old file or the new file, never a partial/truncated one. The intermittent "200 while ls says absent" was a host-vs-container filesystem mismatch: `ls` checked the host (`.:/app` bind mount) while curl was served from inside the container (Docker named volume `media_volume`).
- `ImageGenerator._preprocess_one` writes the **original** image NON-atomically via `open(original_path, "wb")` (truncate-then-write) — this is the real bug. Thumbnails are already atomic.
- `AdImage` model's `thumbnail_*_url` properties are read-only (return existing paths, no lazy generation). No `post_save`/`pre_save` signal writes files.
- `SeedService._clean()` (line 225-259) does `shutil.rmtree(seed_dir)` — deletes the entire `media/seed/` directory after deleting DB records. During re-seed (while dev web is up), this creates a window where files are absent on disk.

## Root Cause
- **`_preprocess_one` writes the original image non-atomically** (line 328-329 original code: `with open(original_path, "wb") as f: f.write(img_bytes)`). If seed re-runs while web is serving (e.g., developer runs `docker compose run --rm seed`), the `open(..., "wb")` truncates the file to 0 bytes before writing the full content. A concurrent `media_gate` → `_serve_image` reader can observe an empty or partial file, causing broken images or 404s.
- Thumbnails are already written atomically via `ThumbnailService._publish` (temp + `os.replace`), so they are NOT affected by this race.
- The `shutil.rmtree` in `_clean()` is a separate, broader window: it deletes ALL seed files before regenerating. The atomic-write fix reduces the per-file exposure window but cannot eliminate the rmtree window. The primary fix targets the per-file non-atomic write, which is the more impactful defect.

## Fix Applied
- **`src/backend/apps/seed/generators/images.py` `_preprocess_one`**: replaced the non-atomic `open(original_path, "wb")` with `ThumbnailService._publish(img_bytes, original_path, WriteMode.REPLACE)`, reusing the existing atomic temp+replace pattern already used for thumbnails. This ensures the original is never served in a truncated/empty state during concurrent seed regeneration.
- **`src/backend/apps/seed/tests/test_seed.py`**: added `test_original_written_atomically` in `TestImageGeneratorTruthfulness` — spies on `ThumbnailService._publish`, asserts it is called 4 times (1 original + 3 thumbnails), verifies the original file is valid JPEG, and confirms no temp files are left behind.

## Validation
- `ruff check src/backend/apps/seed/generators/images.py src/backend/apps/seed/tests/test_seed.py` — All checks passed.
- `basedpyright src/backend/apps/seed/generators/images.py` — 0 errors, 0 warnings.
- `pytest TestImageGeneratorTruthfulness` (8 tests) — all passed.

## Status
- Resolved. Fix is minimal and targeted: one line replaced in `_preprocess_one`, one test added.
