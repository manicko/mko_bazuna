# Evaluation Report: Direct-to-MEDIA_ROOT Seed Photo Download

**Date:** 2026-08-15  
**Subject:** Should `download_seed_photos.py` be changed to download directly to `MEDIA_ROOT/seed/` instead of to `fixtures/images/`?  
**Verdict:** NO (see §2).

---

## 1. Is the 3-stage pipeline unnecessarily complex, or does it serve real architectural purposes?

**Verdict: The 3-stage pipeline serves real, verifiable architectural purposes. It is NOT unnecessarily complex.**

The three stages form a deliberate **source-vs-runtime separation** with a clear responsibility split:

| Stage | Component | Responsibility | Network? | Lives in |
|-------|-----------|----------------|----------|----------|
| **A — Download** | `scripts/download_seed_photos.py` | One-time fetch from Unsplash/Pexels, compress, persist as fixture JPEGs + update JSON manifest/state | YES (once) | Source tree: `src/backend/apps/seed/fixtures/images/` |
| **B — Provision** | `ImageGenerator` (images.py) | Copy bundled fixture JPEGs → `MEDIA_ROOT/seed/`, generate thumbnails, emit `AdImage` ORM rows | NO | Runtime: `MEDIA_ROOT/seed/` (Docker VOLUME) |
| **C — Hash** | `SeedService._backfill_image_hashes` | Compute SHA-256 for `bulk_create`-bypassed hashes | NO | Runtime: `MEDIA_ROOT/seed/` |

### Evidence

**Stage A is standalone by design** (`download_seed_photos.py:20-31`): it imports only `requests`, `PIL`, `json`, `pathlib` — no `django.setup()`, no settings import. It resolves its target directory via `PROJECT_ROOT = Path(__file__).resolve().parent.parent` (line 38), computing `FIXTURES_IMAGES_DIR` as an absolute path under the source tree. This path is correct in both local dev (`C:\py_dev\mko_bazuna\src/backend/apps/seed/fixtures/images`) and inside Docker (`/app/src/backend/apps/seed/fixtures/images`) because the fixtures directory ships inside the Docker image via `COPY . .`.

**Stage B is the Django-bound provisioning step** (`images.py:19` defines its own `FIXTURES_IMAGES_DIR` via `__file__`). It reads fixture JPEGs, writes them to `MEDIA_ROOT/seed/` (via `_ensure_seed_dir` at `images.py:166-174`), generates three thumbnail sizes via `ThumbnailService.generate_thumbnails` (which uses `os.O_CREAT | os.O_EXCL` — atomic, non-overwriting), and stores `AdImage.image = "seed/<filename>"` (`images.py:118,200`).

**Stage C reads back from media** (`seed_service.py:278-281`): `_backfill_image_hashes` computes `Path(media_root) / str(img.image)` → `MEDIA_ROOT/seed/<filename>`, exactly where Stage B wrote it.

### What each stage protects

1. **Reproducibility / no-network invariant.** The spec (`technical-specification.md:184`) states: *"No network dependencies at seed time (all resources bundled)."* The `seed` management command (`manage.py seed`) must run with zero network access. Stage A fetches from third-party APIs (Unsplash/Pexels, using `seed-images-config.json` with API keys at `scripts/seed-images-config.json`); Stages B and C never touch the network. Collapsing A→C would force every seed run to hit external APIs.

2. **Idempotent re-seeding.** `SeedService._clean()` (`seed_service.py:210-218`) wipes `MEDIA_ROOT/seed/` on *every* `--force` re-seed. Because the source JPEGs live in `fixtures/images/` (not in the wiped media dir), re-seeding can re-provision the same images deterministically without re-downloading. If downloads went directly to `media/seed/`, re-seeding would destroy them, forcing a re-download each time — breaking idempotency and re-coupling to the network.

3. **Docker volume hygiene.** The Dockerfile declares `VOLUME ["/app/media"]` (`Dockerfile:140`), and `docker-compose.yml:119` mounts `media_volume:/app/media` to the seed service. Media is **ephemeral runtime state**, never baked into the image. Fixture JPEGs, by contrast, are part of the source tree and ARE baked in via `COPY . .` (confirmed: `.dockerignore` excludes `media/` at line 18 but does NOT exclude `src/backend/apps/seed/fixtures/images/*.jpg`). This is the mechanism that gives the seed command its "all resources bundled" guarantee inside the container.

4. **State persistence across re-downloads.** The download script maintains `downloaded_ids.json` (tracks remote photo IDs to avoid re-fetching) and `photo_manifest.json` (maps category slugs → filenames + dimensions) in the fixtures dir. These JSON files ARE committed to git (verified: `git ls-files` confirms `photo_manifest.json` is tracked; the JPEGs are gitignored per `.gitignore:225-227`). This state must live alongside the JPEGs it describes; moving JPEGs to an ephemeral volume would orphan it.

5. **Test isolation.** Tests override `MEDIA_ROOT` to `tempfile` dirs (`test_seed.py:281` uses `@override_settings(MEDIA_ROOT="/tmp/test_seed_media")`; `test_media_security.py:37` uses a `TemporaryDirectory()` fixture). Tests never invoke the download script. Stage A writes to the source tree (gitignored JPEGs); Stage B writes to the overridden temp MEDIA_ROOT. The two never collide. If Stage A wrote to `MEDIA_ROOT/seed/`, the download script's hardcoded path resolution would bypass `override_settings` entirely, creating a latent contamination vector.

---

## 2. Should `download_seed_photos.py` be changed to download directly to `MEDIA_ROOT/seed/`?

**NO.** Three independent constraints make the current design the correct one.

### Constraint 1 — Path resolution is fundamentally broken by the standalone design

`download_seed_photos.py` is deliberately **standalone** — it runs without Django (`no django.setup()`), so it cannot call `settings.MEDIA_ROOT`. To write to `MEDIA_ROOT/seed/`, it would have to replicate Django's path logic: `BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent.parent` (settings file is at `src/backend/config/settings/base.py`, so `BASE_DIR` = 4 `.parent` hops from the file; `MEDIA_ROOT = BASE_DIR.parent / "media"`). The script is at `scripts/download_seed_photos.py` — a completely different file, so it cannot reuse that derivation. Hardcoding `"<project_root>/media/seed"` is fragile and was explicitly avoided in the current design (the script uses `__file__`-based resolution to its own source-tree target, which happens to be correct in Docker because fixtures ship in the image).

> **This is not merely inconvenient — it is architecturally impossible to do correctly without either importing Django (breaking the standalone design) or hardcoding a path that disagrees with `MEDIA_ROOT` in environments where `MEDIA_ROOT` is overridden.**

### Constraint 2 — The "no network at seed time" contract is violated

The spec (`technical-specification.md:184`) explicitly bundles the "no runtime network dependency" requirement. The `seed` service in `docker-compose.yml:95-120` runs `entrypoint-seed.sh` → `manage.py seed --force` with **no API keys injected** (the only env vars are `SEED_USERS`/`SEED_ADS`/DB config). Collapsing the pipeline means seeding requires live Unsplash/Pexels access + the gitignored `seed-images-config.json` (which is NOT in `.dockerignore`'s `env*` pattern, meaning it would be accidentally baked into production images — a separate pre-existing concern). The design's core guarantee — "seed works offline in any environment with the source tree" — is annihilated.

### Constraint 3 — `_clean()` destroys downloaded photos on re-seed

`SeedService._clean()` (`seed_service.py:210-218`) calls `shutil.rmtree(seed_dir)` on `MEDIA_ROOT/seed/`. This runs on **every** `seed --force` invocation (including the dev override at `docker-compose.dev.override.yml:48-49` which auto-runs seed after catalog load). If photos lived only in `media/seed/`, the first re-seed would delete them and the second would have nothing to seed — unless it re-downloaded. The two-stage design exists precisely so that **re-seeding is free** (re-copy from stable fixtures) rather than requiring re-fetching.

### What would need to change if we proceeded anyway (for completeness)

If the team overrode the constraints above, the blast radius would be:

- **Download script** (`download_seed_photos.py`): replace `FIXTURES_IMAGES_DIR` resolution with a `MEDIA_ROOT`-equivalent. Would need an env var or `os.environ["MKO_MEDIA_ROOT"]` fallback. The `photo_manifest.json`/`downloaded_ids.json`/`query_hierarchy.json` would need to move out of `fixtures/images/` to stay committed (they're metadata, not media).
- **`ImageGenerator._preprocess_images`** (`images.py:176-224`): eliminate the read-from-fixture / write-to-media copy; instead just check existence in `seed_dir` directly and generate thumbnails. The `FIXTURES_IMAGES_DIR` constant would become dead code.
- **`test_seed.py`**: `TestImageGenerator.test_generates_ad_images` (`test_seed.py:282-315`) currently materializes dummy JPEGs in `FIXTURES_IMAGES_DIR` because `ImageGenerator` reads from there. This test would break — it would need to materialize into the temp `MEDIA_ROOT` instead.
- **`SeedService._backfill_image_hashes`**: unchanged (still reads from `MEDIA_ROOT/seed/`).
- **`.gitignore`**: would need a rule for `media/seed/` JPEGs (already present at line 230, but would now apply to *downloaded* photos, not just generated ones).
- **Docker**: the download step would need to be inserted into `entrypoint-seed.sh` before `manage.py seed`, with API keys injected as secrets. The `VOLUME ["/app/media"]` would need to be populated before seeding.
- **Determinism**: the download script uses `random` for query composition (no fixed seed in `main()` — `download_seed_photos.py` doesn't seed `random`), so re-downloads produce different photos each time. The current design downloads once and freezes the result; direct download would make seeding non-deterministic.

---

## 3. Top 3 concrete risks of collapsing the pipeline (ranked by severity)

### Risk 1 — Seeding becomes dependent on third-party APIs (CRITICAL)

The `seed` management command is used in **development auto-seed** (`docker-compose.dev.override.yml:48` auto-runs seed on `docker compose up`), in **CI test setup** (`docker-compose.test.yml`), and in **one-shot production demo** (`docker-compose.yml:95` `profiles: ["seed"]`). None of these inject Unsplash/Pexels API keys. Collapsing the pipeline turns a previously offline, deterministic operation into one that requires:
- Valid API keys (currently only in the gitignored `scripts/seed-images-config.json`, local dev only)
- Live internet access (unavailable in CI air-gaps, offline dev environments, or production containers)
- Rate-limit tolerance (Unsplash caps at 45 reqs/h per `downloaded_ids` tracking; Pexels at 800/day with 20k/month hard limit)

**Impact:** Seed fails entirely without network/keys. This is a hard blocker for CI, offline development, and production demo deployments.

### Risk 2 — Re-seeding silently destroys seed data (HIGH)

`SeedService._clean()` (`seed_service.py:210-218`) does `shutil.rmtree(seed_dir)` unconditionally. In the dev override, seed auto-runs on every `docker compose up`. With direct download, the flow would be:
1. `docker compose up` → seed runs → downloads → provisions → creates DB rows
2. Developer makes a config change, runs `docker compose up` again → `_clean()` wipes `MEDIA_ROOT/seed/` → re-download → **new random photos** (script doesn't seed `random`) → different images each time → non-deterministic demos

Even if the developer remembers to back up `media/seed/` externally, the `_clean()` call is unconditional and there is no "preserve downloaded photos" flag. The current design survives this because fixtures are in a separate, non-wiped directory.

**Impact:** Non-deterministic seed data across re-seeds; lost work if the media volume is ephemeral (which it is — it's a Docker VOLUME, not persisted in the image).

### Risk 3 — Test contamination and broken fixture contract (MEDIUM)

Three tests directly depend on the fixtures-vs-media separation:

1. **`test_seed.py:282` (`TestImageGenerator.test_generates_ad_images`)**: explicitly materializes dummy JPEGs in `FIXTURES_IMAGES_DIR` because `ImageGenerator._preprocess_images` reads from there. The test comment says *"The actual image files were removed from git; only the JSON manifest remains"* and *"ImageGenerator._preprocess_images silently skips missing files."* If the script wrote to `media/seed/` instead, this test's fixture-materialization would target the wrong directory, and `ImageGenerator` would silently skip all photos (returning 0 images), causing `test_image_keys_have_correct_format` (`test_seed.py:320`) to fail with empty results.

2. **`test_seed.py:866` (`TestSeedCommandEnhanced.test_media_cleanup`)**: verifies that `_clean()` wipes `MEDIA_ROOT/seed/` of stale files and recreates it. This test writes a dummy file to the temp `MEDIA_ROOT/seed/` and confirms it's gone after re-seed — it explicitly tests the *wipe* behavior that would destroy downloaded photos.

3. **`test_media_security.py`**: uses `seed/kvartiry_01.jpg` as a storage key (`test_media_security.py:258`) — the `"seed/<filename>"` key format must be preserved regardless of the download mechanism.

**Impact:** At minimum 2-3 test failures requiring non-trivial test rewrites; more importantly, the semantic boundary between "bundled source fixtures" (committed JSON + gitignored JPEGs) and "runtime media" (ephemeral VOLUME) would dissolve, making future maintenance ambiguous.

---

## 4. Alternative improvement: preserve the 3-stage architecture, reduce friction

The 3-stage design is correct. The friction is operational, not architectural. These changes preserve the design while making it smoother:

### A. Centralize the fixtures-image path constant

`FIXTURES_IMAGES_DIR` is currently defined **twice** with independent derivations:
- `download_seed_photos.py:40`: `PROJECT_ROOT / "src" / "backend" / "apps" / "seed" / "fixtures" / "images"` (PROJECT_ROOT = `__file__` two levels up)
- `images.py:19`: `Path(__file__).resolve().parent.parent / "fixtures" / "images"` (relative to images.py itself)

Both resolve to the same directory, but they're computed independently and could drift. **Improvement:** Move `FIXTURES_IMAGES_DIR` (and the manifest/IDs/query-hierarchy paths) into a single small module under `apps.seed`, e.g. `apps/seed/paths.py`, that both the download script and `ImageGenerator` can import. The download script already imports from `apps.ads.models` indirectly (via the manifest it produces); making it import `from apps.seed.paths import FIXTURES_IMAGES_DIR` would require Django setup — but that's acceptable if the script's `__main__` block calls `django.setup()` only when invoked as `python -m` from within the project (a minor concession for correctness). Alternatively, keep it standalone but document the single source of truth.

### B. Add a `--check` / manifest-validation mode to the download script

The script currently warns on missing fixture files but doesn't report *how many* manifest-referenced photos are missing. Add a `--validate` subcommand that cross-checks `photo_manifest.json` against actual files on disk and reports missing JPEGs. This makes the "partial download" state visible without re-running.

### C. Document the seed-photo workflow end-to-end

There is no documentation (README, Makefile target, or docs page) describing the **order** in which to:
1. Run `download_seed_photos.py` locally (with `seed-images-config.json`)
2. Commit `photo_manifest.json` / `query_hierarchy.json` / `downloaded_ids.json`
3. Run `docker compose build` to bake JPEGs into the image
4. Run `docker compose --profile seed run --rm seed`

The Dockerfile's `COPY . .` bakes the entire source tree into the image (`Dockerfile:54`). The `.dockerignore` excludes `media/` (line 18) but does NOT exclude `src/backend/apps/seed/fixtures/images/*.jpg` — so fixture JPEGs present on disk ARE baked into the Docker image. This is the mechanism that gives the seed command its "all resources bundled" guarantee. This fact is subtle and easy to get wrong (one might assume `.dockerignore` or `.gitignore` excludes the JPEGs, but neither does in the Docker build context). A `docs/99-agent/seed-images-workflow.md` or a `Makefile` target (`make seed-photos`) would codify the order and prevent accidental omission.

### D. Optional: Make `ImageGenerator._preprocess_images` log a summary count

Currently it emits per-file `"Photo file not found: %s, skipping"` warnings (`images.py:197`) but no aggregate summary. Adding a count of "N skipped, M processed" at the end of `generate()` would make the partial-fixture situation immediately visible during seeding.

### E. Fix the print() in the download script

`download_seed_photos.py:550` uses `print()` instead of the logger, violating project rule #12 (`No print() Statements`). This is a trivial fix to the existing script that improves consistency with the rest of the codebase.

---

## Summary

The 3-stage pipeline (download-to-fixtures → copy-to-media → read-from-media) is **not over-engineered**. It implements a standard **build-time vs. runtime separation** that is baked into the project's Docker, test, and operational design. The proposal to collapse it into a direct download-to-`MEDIA_ROOT/seed/` would:

- Break the **"no network dependency at seed time"** invariant (spec line 184),
- Defeat **idempotent re-seeding** (`_clean()` wipes `media/seed/` on every run),
- Make path resolution **architecturally impossible** without coupling the standalone script to Django settings,
- Break **3 existing tests** that depend on the fixtures-vs-media boundary.

**Recommendation:** Do not change the pipeline. Adopt improvement §4A (centralize the fixtures path) and §4C (document the workflow) to reduce the operational friction that likely motivated the proposal, while preserving the architectural integrity that the spec, Docker setup, and test suite all depend on.
