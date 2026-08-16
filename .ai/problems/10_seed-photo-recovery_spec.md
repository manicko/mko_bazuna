# Specification: Seed Photo Recovery — Manifest Cleanup for Missing Fixture Files

**File:** `10_seed-photo-recovery_spec.md`
**Status:** Final (ready for implementation planning)
**Date:** 2026-08-15

---

## 1. Problem Statement

The seed photo download script (`scripts/download_seed_photos.py`) ships with a `--validate` mode that checks whether every photo referenced in `photo_manifest.json` has a corresponding JPEG file on disk. When run, it reports **370 missing files** out of 764 manifest entries (418 files exist on disk).

These missing JPEGs were caused by a combination of factors:
- **JPEG files are gitignored** (`.gitignore` lines 225–227 ignore `*.jpg`/`*.jpeg`/`*.png` in fixture directories). A fresh clone or `git clean -fdx` wipes all JPEGs while the manifest (JSON, tracked in git) retains references to them.
- **Accidental deletion** of fixture files after a successful download.
- **Interrupted downloads**: the manifest is saved only after an entire pass completes (`save_manifest` at line 744), so killing the script mid-pass can leave the manifest referencing files that were never written, or orphan files on disk that aren't in the manifest.

The downstream impact is in `ImageGenerator` (`src/backend/apps/seed/generators/images.py`): `_preprocess_images()` silently skips missing fixture files (line 241–243, logging a WARNING), which means ads in categories that have lost all their photos receive **zero `AdImage` records** — no images appear on those ads in the dev environment. The current `--validate` mode is read-only and offers no recovery action.

**Root cause**: There is no mechanism to reconcile `photo_manifest.json` with files on disk when files go missing. The manifest is never pruned of stale entries.

---

## 2. Confirmed Requirements

### 2.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR01 | A `--fix=cleanup` mode that removes manifest entries for files missing from disk | Must |
| FR02 | A `FixMode(StrEnum)` with at least `NONE` and `CLEANUP` values, following the project's StrEnum convention (rule 10) | Must |
| FR03 | `--validate --fix=cleanup` runs validation, removes stale entries, then re-validates | Must |
| FR04 | The `--fix=cleanup` mode must NOT require API keys or network access (purely local file operations) | Must |
| FR05 | After cleanup, `--validate` must report 0 missing manifest-referenced files | Must |
| FR06 | Categories that lose all their photos must be reported as a WARNING (not silently empty) | Should |
| FR07 | The manifest must be saved atomically (write to temp file, then rename) to prevent partial writes on interruption | Should |
| FR08 | `downloaded_ids.json` must NOT be modified by `--fix=cleanup` | Must |

### 2.2 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR01 | Dev-only operation — the download script is already dev-only (no production impact) |
| NFR02 | Follow existing CLI argument pattern (`--flag=value` via `sys.argv` parsing, consistent with `--category=` and `--validate`) |
| NFR03 | Follow the project's existing test pattern in `test_download_seed_photos.py` |
| NFR04 | No new dependencies — only Python stdlib + existing project imports |
| NFR05 | No changes to `ImageGenerator`, `SeedService`, or any Django-bound code |

---

## 3. Conceptual Development Tasks

### Task 1: Add `FixMode` StrEnum and `--fix` CLI flag

**Purpose:** Introduce a typed enum for fix modes and wire up CLI parsing.

**Expected outcome:**
- A `FixMode(StrEnum)` class with `NONE = "none"` and `CLEANUP = "cleanup"` defined in `download_seed_photos.py`.
- Extended `sys.argv` parsing in `main()` to recognize `--fix=<mode>` (following the existing `--category=X` pattern at lines 646–652).
- A `fix_mode` variable defaulting to `FixMode.NONE`.

**Dependencies:** None.

### Task 2: Refactor manifest entry access into reusable helpers

**Purpose:** Extract file-existence check logic so it can be shared between validation and fix modes.

**Expected outcome:**
- A `find_missing_manifest_entries(manifest: dict) -> list[tuple[str, dict]]` function that iterates all categories in the manifest (including `default`), checks `FIXTURES_IMAGES_DIR / filename` for existence, and returns a list of `(category_slug, photo_entry)` tuples for missing files.
- The existing `validate_manifest()` function's Check 1 logic is refactored to use `find_missing_manifest_entries()`, preserving identical behavior (logging, exit codes).

**Dependencies:** None (refactor of existing code).

### Task 3: Implement `fix_cleanup()` function

**Purpose:** Remove stale manifest entries for files missing from disk.

**Expected outcome:**
- A `fix_cleanup(manifest: dict) -> int` function that:
  - Iterates all categories in the manifest.
  - Filters out photo entries where `FIXTURES_IMAGES_DIR / entry["filename"]` does not exist.
  - Logs a WARNING for any category that ends up with zero photos.
  - Saves the manifest via `save_manifest()` using atomic write (temp file + rename).
- Returns the count of removed entries.

**Dependencies:** Task 2 (uses `find_missing_manifest_entries` indirectly, or shares the existence-check pattern).

### Task 4: Wire `--fix=cleanup` into `main()`

**Purpose:** Integrate the cleanup mode into the script's entry point.

**Expected outcome:**
- In `main()`, when `--validate --fix=cleanup` is passed:
  1. Run validation to report current missing files.
  2. Call `fix_cleanup(manifest)` to remove stale entries.
  3. Re-run validation to confirm 0 missing files remain.
  4. Exit with code 0 if clean, non-zero if still missing (e.g., categories with zero photos that can't be cleaned further).
- When `--fix=cleanup` is passed without `--validate`:
  1. Load the manifest.
  2. Call `fix_cleanup(manifest)`.
  3. Run a post-cleanup validation pass to confirm.
- `--fix=cleanup` alone (without `--validate`): loads manifest, runs cleanup, saves, reports summary.

**Dependencies:** Tasks 1, 2, 3.

### Task 5: Add tests for cleanup mode

**Purpose:** Ensure the cleanup logic is correct and resilient.

**Expected outcome:**
- New `TestFixCleanup` class in `test_download_seed_photos.py` with tests for:
  - `find_missing_manifest_entries()` — returns correct missing entries with category scope.
  - `fix_cleanup()` — removes only missing entries, preserves existing entries.
  - `fix_cleanup()` — logs WARNING when a category goes to zero photos.
  - `fix_cleanup()` — returns correct count of removed entries.
  - Atomic write — manifest is not corrupted if the function is called with mixed existing/missing files.
  - `--fix=cleanup` end-to-end with mocked filesystem (temp directory, fake JPEG files).
  - `downloaded_ids.json` is NOT modified by cleanup.

**Dependencies:** Tasks 1–4.

### Task 6: Document the recovery workflow

**Purpose:** Ensure developers know how to use the new recovery mode.

**Expected outcome:**
- Update the docstring at the top of `download_seed_photos.py` to document the `--fix=cleanup` mode and its usage:
  ```
  uv run python scripts/download_seed_photos.py --validate --fix=cleanup  # find and clean missing files
  ```
- Add a note to `docs/ops/seed-workflow.md` (if it exists) or the LLM task (`seed-content-generation.md`) about the cleanup workflow for the accidental-deletion scenario.

**Dependencies:** Tasks 1–4.

---

## 4. Product Owner Decisions

| # | Question | Decision (Recommended Default) | Rationale |
|---|----------|-------------------------------|-----------|
| D1 | When `--validate` detects missing files, should the system offer a `--fix=cleanup` mode that removes stale manifest entries? | **YES — `cleanup` mode.** | Directly addresses the root cause (manifest/disk inconsistency). No API keys, network, or schema changes needed. Recommended by research as Approach A. |
| D2 | Should `--fix=cleanup` also remove IDs from `downloaded_ids.json` to allow re-download? | **NO.** IDs are left untouched. Users who want fresh photos use `--all` to re-download for under-covered categories. | Keeping IDs prevents re-fetching rejected/unsuitable photos. Cleanup is about manifest hygiene, not re-downloading. |
| D3 | Should the system add a `rejected_ids.json` file for permanently rejected photos? | **NO.** Not needed for this problem. | Overengineering for a dev-only tool. No existing code references rejected IDs. A simple skip-list (`downloaded_ids.json`) suffices. |
| D4 | Should `--fix=cleanup` also remove orphaned JPEGs (on disk but not in manifest)? | **NO.** Cleanup only prunes the manifest, never deletes files. | File deletion is destructive and irreversible. Orphans are harmless (ImageGenerator never reads them). Manual removal is safer. |
| D5 | Should `--validate` after cleanup still check hierarchy coverage (categories with zero manifest entries)? | **YES — unchanged.** Coverage check remains strict. | Coverage check is separate from file-existence check. Categories without photos are reported but not auto-fixed (requires API re-download). |
| D6 | Should the manifest be saved atomically (temp file + rename)? | **YES.** | Prevents corruption on interruption, especially important for a file tracked in git. |
| D7 | Should categories that lose all photos during cleanup be treated as errors (exit 1) or warnings? | **WARNING, not error.** | A category with zero photos is a data-quality issue, not a crash. `--validate` should still report it under Check 2 (coverage) but not block the cleanup process. |
| D8 | Should `--fix=cleanup` be combinable with `--category=<slug>` to restrict cleanup to one category? | **NO for v1.** Apply to all categories. | Adds complexity without clear benefit. The full cleanup is fast (manifest is ~770 lines). Category-scoped fix can be added later if needed. |

---

## 5. Research Summary

Three researcher tasks were completed in parallel. Summary of key findings:

### 5.1 Seed Photo Pipeline Architecture (Research Task 1)

**Key findings:**

1. **Three independent state files with no cross-referencing:**
   - `photo_manifest.json` (764 entries, git-tracked) — maps category slugs → photo filenames with dimensions
   - `downloaded_ids.json` (776 IDs, git-tracked) — flat global set of API photo IDs (`pexels_XXX`, `unsplash_XXX`) to skip re-download
   - `query_hierarchy.json` (205 categories, git-tracked) — query composition rules per category

   **There is no `photo_id` field in the manifest.** The manifest stores only `{filename, width, height}`. There is no way to trace a manifest entry back to its source API ID.

2. **The re-download blocker:** When `photo_source.downloaded_ids.add(pid)` is called (line 509) *before* `download_and_compress()` (line 520), the API ID is permanently marked as downloaded even if the download fails. And when files are missing, `pick_photo()` (line 356) filters by `downloaded_ids` — but the missing files' IDs are in that set, so they can never be re-selected.

3. **ImageGenerator silently degrades:** `_preprocess_images` logs `WARNING: Photo file not found` and skips (line 241–243). Categories with all-missing photos get zero `AdImage` records (line 141–150) — no crash, just missing images on seed ads.

4. **No existing fix mode.** Grep for "fix" in `download_seed_photos.py` returns only the docstring path description and the `--validate` warning message. The only CLI modes are: default, `--all`, `--category=X`, `--validate`.

### 5.2 Best Practices for Seed Fixture Recovery (Research Task 2)

**Key findings:**

1. **Content-addressable storage (CAS)** using SHA-256 content keys is the gold standard for deduplication and resumability — the project already has `FileHashService` and `AdImage.sha256` field, but these are used in Stage C (ImageGenerator), not in the download script.

2. **Django management commands** should be idempotent, use `transaction.atomic()` with `--dry-run`, `get_or_create`, and `iterator(chunk_size=500)`. The download script is standalone (no Django), so these patterns don't directly apply but inform the design philosophy.

3. **Lockfile/skip-list patterns** (npm `package-lock.json`, Composer `composer.lock`) use a committed lockfile + gitignored output. The project follows this: JSON state files are committed, JPEGs are gitignored.

4. **CI validation** should run `--validate` as a pre-build step to catch missing fixtures before Docker builds.

### 5.3 Approach Comparison (Research Task 3)

Three approaches were evaluated in detail:

| Dimension | Approach A: Cleanup | Approach B: Re-download | Approach C: Rejected IDs |
|---|---|---|---|
| State files changed | 1 (manifest) | 2 (manifest + downloaded_ids) | 3 (manifest + downloaded_ids + rejected_ids) |
| Schema change | None | `photo_id` field needed | `photo_id` field needed |
| API/network dependency | No | Yes | Yes (redownload only) |
| New files | 0 | 0 | 1 (`rejected_ids.json`) |
| Lines of new code | ~40 | ~80 + schema | ~100 + schema |
| Atomicity risk | Low | Medium | High |
| ImageGenerator changes | None | None | None |
| **Recommended** | **YES** | Future enhancement | No — overengineered |

**Recommendation: Approach A (manifest cleanup only).** Rationale:
- Directly addresses the root cause (manifest/disk inconsistency) with ~40 lines of code
- No schema change, no API dependency, works offline and in CI
- The 370 existing missing entries predate any `photo_id` addition — Approaches B and C can't recover their original IDs anyway
- `--fix=cleanup` provides the clean baseline; re-download (Approach B) can be added later as a sequential enhancement
- Minimal test surface — only new tests in `test_download_seed_photos.py`, no existing tests broken

---

## 6. Assumptions

1. The `download_seed_photos.py` script is a **development-only** tool — it is never run in production. (Verified: it's in `scripts/`, not in `src/backend/`, and requires Unsplash/Pexels API keys that are not deployed.)
2. The manifest's `categories` dict and `default` dict are the only locations where photo entries exist. (Verified at lines 569–582 in `download_seed_photos.py`.)
3. The `FixMode(StrEnum)` can be defined inline in the standalone script using Python 3.14's stdlib `enum.StrEnum`, without importing Django. (The script already avoids Django imports by manipulating `sys.path` to access `apps.seed.paths` directly.)
4. Atomic writes via `tempfile.NamedTemporaryFile` + `os.replace` are available on all target platforms (Linux/macOS/Windows). (Verified: the project targets Docker Linux containers primarily, with Windows for dev.)
5. The `find_missing_manifest_entries()` function can be used to refactor the existing `validate_manifest()` Check 1 without changing its external behavior (same log messages, same exit code).
6. Categories that go to zero photos after cleanup should still appear in the manifest with `{"photos": []}` — they are valid empty categories, not errors. The coverage check (Check 2) in `validate_manifest()` already handles reporting uncovered categories.

---

## 7. Constraints

1. **StrEnum for all constants** (project rule 10): `FixMode` must use `StrEnum`, not plain strings or dicts.
2. **No `print()` statements** (project rule 12): use `logger = logging.getLogger(__name__)`.
3. **English only** (project rule 1): all comments, logs, docstrings must be in English.
4. **Small functions** (project rule 4): each new function should be focused on one thing.
5. **No new dependencies**: only Python stdlib + existing project imports (`enum`, `os`, `json`, `logging`, `pathlib`).
6. **Git-tracked state files**: `photo_manifest.json` and `downloaded_ids.json` are committed to git. `rejected_ids.json` is NOT introduced (per decision D3).
7. **The script is standalone**: it must not require `django.setup()` or import Django models. It only imports `apps.seed.paths` (which is explicitly Django-free per its docstring).

---

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Manifest corruption from interrupted write | Low | Low | Use atomic write (temp file + `os.replace`). |
| Category goes to zero photos, silently degrades dev UX | Medium | Medium | Log WARNING for categories that become empty. Coverage check in `--validate` reports them. |
| User runs `--fix=cleanup` and loses photo pool without re-downloading | Medium | Low | Document clearly in docstring and workflow docs. `--all` flag exists for re-downloading. |
| Test creates dummy JPEGs from manifest — fewer entries after cleanup | Low | None | Tests dynamically create dummy files from manifest entries; fewer entries = fewer dummy files. No test breakage. |
| Orphaned JPEGs (on disk, not in manifest) left behind | Low | Low | Documented as intentional — cleanup never deletes files. Orphans are harmless. |
| `downloaded_ids.json` grows stale with IDs for deleted/missing photos | Low | Medium | Not addressed by this spec — IDs remain, preventing re-download of specific photos. Acceptable since `--all` downloads new photos regardless. |

---

## 9. Open Questions

1. **Should `--fix=cleanup` also offer a `--fix=redownload` variant for restoring photos?** — This would require adding `photo_id` to the manifest schema (Approach B from research). Deferred to a future spec; Approach A provides the clean baseline first.
2. **Should the download script seed `random` for deterministic re-download?** — The current script does not call `random.seed()`, so re-downloads produce different photos each run. This is a pre-existing issue, not introduced by this change.

---

## 10. Out of Scope

- **Re-download mode**: Adding `--fix=redownload` that removes IDs from `downloaded_ids.json` and fetches new photos. Requires `photo_id` in manifest schema, API keys, and network access. Can be built as a sequential enhancement after cleanup.
- **Rejected IDs list**: A `rejected_ids.json` file for permanently excluding photos. Deemed unnecessary by research.
- **Orphaned file cleanup**: Removing JPEGs from disk that exist but aren't referenced in the manifest. Cleanup only prunes the manifest — never deletes files.
- **Photo content quality filtering**: No mechanism to reject photos based on content (wrong topic, poor quality). The existing `downloaded_ids.json` skip-list is the de facto rejection mechanism.
- **ImageGenerator changes**: The `ImageGenerator` silently skips missing files. This behavior is unchanged — after cleanup, all manifest-referenced files exist, so no skipping occurs.
- **Docker/seed workflow changes**: The `SeedService._clean()` method wipes `MEDIA_ROOT/seed/` (not fixture paths). No changes needed there.

---

## 11. Definition of Ready

This specification is **ready for implementation planning** when:

- [x] Business problem is clearly stated (manifest/disk inconsistency with 370 missing files, no recovery mechanism)
- [x] All requirements are confirmed (FR01–FR08, NFR01–NFR05)
- [x] 6 conceptual development tasks are defined with purpose, expected outcome, and dependencies
- [x] 8 Product Owner decisions are captured (with recommended defaults)
- [x] Research has been conducted (3 parallel researcher tasks) and summarized
- [x] Assumptions, constraints, risks, open questions, and out-of-scope items are documented
- [x] The recommended approach (Approach A: manifest cleanup only) is justified by evidence

**Implementation may begin — no additional business analysis is required.**