# Photo Thumbnail Generation — Implementation Verification Report

**Plan:** `.ai/plans/02/Photo Thumbnail Generation/plan.md`
**Date:** 2026-07-29
**Scope:** Verify plan implementation against actual codebase. No code changes made.

---

## Executive Summary

The plan defines 17 tasks (T1.1–T5.3) across 5 phases. **11 tasks are implemented** (with varying degrees of deviation), **3 tasks are missing**, and **3 tasks are partially implemented**. The core thumbnail generation pipeline works end-to-end (upload → generate → store → moderate), but two critical gaps prevent thumbnails from being served to end users: templates still reference full-size images, and `media_gate()` cannot resolve thumbnail storage keys.

| Phase | Tasks | Status |
|-------|-------|--------|
| Phase 1: Schema & Constants | T1.1, T1.2 | ✅ Both implemented |
| Phase 2: Service Layer | T2.1, T2.2, T2.3 | ✅ T2.1/T2.3 fully; T2.2 with deviations |
| Phase 3: Model & Integration | T3.1, T3.2, T3.3 | ✅ T3.1/T3.3 fully; T3.2 partial |
| Phase 4: Backfill | T4.1 | ❌ Missing |
| Phase 5: Templates | T5.1, T5.2, T5.3 | ✅ T5.3 only; T5.1/T5.2 missing |

---

## Phase 1: Schema & Constants

### T1.1: Create ThumbnailSizeStrEnum — ✅ IMPLEMENTED

**Plan anchor:** `src/backend/apps/core/enums.py`
**Actual location:** `src/backend/apps/core/enums.py:74-79`

```python
class ThumbnailSizeStrEnum(StrEnum):
    """Standard thumbnail sizes for Mko Bazuna."""
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
```

- Uses `StrEnum` as required by research fix #1 (not plain `ThumbnailSize`).
- Exported in `__all__` at line 176.
- Matches plan specification exactly.

### T1.2: Migration + Model Fields — ✅ IMPLEMENTED (with numbering deviation)

**Plan anchor:** `src/backend/apps/ads/migrations/0004_adimage_thumbnails.py`
**Actual file:** `src/backend/apps/ads/migrations/0007_adimage_thumbnails.py`

The migration exists but is numbered `0007` instead of the planned `0004`. This is because migrations `0004_ad_i18n_columns.py`, `0005_multi_lang_search_vector.py`, and `0006_backfill_translations.py` were added between the plan's conception and implementation. The numbering deviation is cosmetic — the migration is functionally correct.

**Migration contents** (`0007_adimage_thumbnails.py`):
- Adds three nullable `CharField(max_length=64, blank=True, null=True)` fields to `AdImage`.
- Help text includes the `<uuid>-<size>.jpg` pattern as specified.
- Depends on `0006_backfill_translations` (correct sequential dependency).

**Model fields** (`models.py:361-378`):
- `thumbnail_small`, `thumbnail_medium`, `thumbnail_large` — all nullable CharFields.
- Match the plan's T1.2 and T3.3 specifications exactly.

---

## Phase 2: Service Layer

### T2.1: Create Media App Structure — ✅ IMPLEMENTED

**Plan anchor:** `src/backend/apps/media/`

Directory structure verified:
```
apps/media/
├── __init__.py              ✅ (empty)
├── apps.py                  ✅ (MediaConfig with name="apps.media")
├── management/
│   ├── __init__.py          ✅ (empty)
│   └── commands/
│       ├── __init__.py      ✅ (empty)
│       └── (backfill_thumbnails.py MISSING — see T4.1)
├── services/
│   ├── __init__.py          ✅ (empty)
│   └── thumbnails.py        ✅ (see T2.2)
└── tests/
    ├── __init__.py          ✅ (empty)
    └── test_thumbnails.py   ✅ (see T2.3)
```

- `apps.media` registered in `INSTALLED_APPS` at `base.py:100`.
- `MediaConfig` properly configured with `name = "apps.media"`.

### T2.2: Implement ThumbnailService — ✅ IMPLEMENTED (with deviations)

**Plan anchor:** `src/backend/apps/media/services/thumbnails.py`
**Actual file:** `src/backend/apps/media/services/thumbnails.py` (100 lines)

**Implemented research fixes:**
| Fix | Status | Evidence |
|-----|--------|----------|
| `ThumbnailSizeStrEnum` (not `ThumbnailSize`) | ✅ | Imported from `apps.core.enums` (line 15) |
| `Image.Resampling.LANCZOS` constant | ✅ | `RESAMPLING = Image.Resampling.LANCZOS` (line 23) |
| Quality=85 | ✅ | `QUALITY = 85` (line 21) |
| Progressive JPEG | ✅ | `PROGRESSIVE = True` (line 24); `progressive=self.PROGRESSIVE` in save (line 87) |
| Storage key `<uuid>-<size>.jpg` | ✅ | `key = f"{stem}-{size_enum.value}.jpg"` (line 75) |
| Atomic writes (`O_CREAT \| O_EXCL \| O_WRONLY`) | ✅ | Lines 91-98 |

**Deviations from plan:**
1. **Instance-based API instead of static methods.** The plan specifies `@staticmethod` for `generate_thumbnails()` and `_atomic_write()`. The actual implementation uses an instance method with `__init__(self, storage_dir: str)` injection. This is a *better* design (more testable, no global state), but differs from the plan's code snippet.

2. **No `_atomic_write` helper method.** The plan describes a separate `_atomic_write(storage_key, image)` static method. The actual code inlines the atomic write logic within `generate_thumbnails()`. Functionally equivalent.

3. **No `ThumbnailGenerationError` exception.** The plan specifies a custom `ThumbnailGenerationError(Exception)` class. The actual code raises `ValueError` for invalid images and lets `FileExistsError` propagate. The custom exception is absent.

4. **No `structlog` logging.** The plan's code snippet imports `structlog` and creates a logger. The actual code has no logging whatsoever in `thumbnails.py`.

5. **EXIF orientation correction added (improvement over plan).** The plan states "Input bytes already EXIF-stripped" and notes thumbnails don't need EXIF handling. The actual code calls `ImageOps.exif_transpose(image)` (line 67) as a defensive measure. This is harmless (idempotent on already-corrected images) and adds robustness.

6. **Background color handling NOT implemented.** Research fix #6 requires white background padding for non-square images. The plan's code snippet shows a canvas-based approach:
   ```python
   canvas = Image.new('RGB', (width, height), (255, 255, 255))
   canvas.paste(thumbnail, offset)
   ```
   The actual code uses `resized.thumbnail(dimensions, self.RESAMPLING)` which preserves aspect ratio but does **not** pad to exact dimensions. Non-square images produce thumbnails smaller than the target box (e.g., a 16:9 image at SMALL size produces 240×135, not 240×180).

   This deviation is consistent with research.md §4.2 note (line 340): *"the simpler one is `thumbnail()` without canvas padding"* and templates use `object-fit: cover` CSS. However, the plan's T2.2 code snippet and research fix #6 explicitly require background color handling, making this a **plan deviation**.

**Summary: T2.2 is functionally complete for thumbnail generation, but misses background color padding, the custom exception, and logging.**

### T2.3: Unit Tests — ✅ IMPLEMENTED (with deviation)

**Plan anchor:** `src/backend/apps/media/tests/test_thumbnails.py`
**Actual file:** `src/backend/apps/media/tests/test_thumbnails.py` (126 lines)

Tests present:
| Test | Covers |
|------|--------|
| `test_small_thumbnail_generation` | ✅ SMALL variant (240×180) |
| `test_medium_thumbnail_generation` | ✅ MEDIUM variant (640×480) |
| `test_large_thumbnail_generation` | ✅ LARGE variant (1280×960) |
| `test_aspect_ratio_preservation` | ✅ Aspect ratio (2:1) preserved |
| `test_progressive_jpeg_output` | ✅ Progressive JPEG flag |
| `test_invalid_image_handling` | ✅ ValueError on bad input |

**Deviation:** The plan's task YAML (TASK_042) lists `test_aspect_ratio_with_background` as a goal, but the actual test `test_aspect_ratio_preservation` checks that aspect ratio is preserved *without* padding (asserts `w <= 240` and `h <= 180`, not `w == 240` and `h == 180`). This is consistent with the T2.2 implementation (no background padding) but contradicts the plan's research fix #6.

**Missing test coverage:**
- No test for atomic write collision (`FileExistsError` retry).
- No test for background color handling (because it's not implemented).

---

## Phase 3: Model & Integration

### T3.1: AdImage URL Properties — ✅ IMPLEMENTED

**Plan anchor:** `src/backend/apps/ads/models.py`
**Actual location:** `src/backend/apps/ads/models.py:392-408`

```python
@property
def thumbnail_small_url(self) -> str | None:
    if self.thumbnail_small:
        return f"{settings.MEDIA_URL}{self.thumbnail_small}"
    return None
```

- All three properties (`thumbnail_small_url`, `thumbnail_medium_url`, `thumbnail_large_url`) implemented.
- Return type `str | None` as specified.
- `settings` already imported at top of file (line 15).
- Matches plan exactly.

### T3.2: Integrate with save_photo() and update_ad_and_moderate() — ⚠️ PARTIALLY IMPLEMENTED

**Plan anchor:** `src/telegram_bot/handlers/ad_create.py`
**Actual file:** `src/telegram_bot/handlers/ad_create.py` (657 lines)

**What the plan wanted:**
1. Replace `save_photo()` with `save_photo_with_thumbnails()` that returns `tuple[str, dict[ThumbnailSizeStrEnum, str]]`.
2. Update `_update_and_moderate()` to pass thumbnail keys to `AdImage.objects.create()`.

**What was actually implemented:**
1. ❌ `save_photo_with_thumbnails()` was **not created**. `save_photo()` (line 454) remains unchanged — it strips EXIF and writes the original only, no thumbnail generation.
2. ✅ `ThumbnailService` imported (line 31).
3. ✅ `ThumbnailSizeStrEnum` imported (line 19).
4. ✅ Thumbnail generation integrated into `_update_and_moderate()` (lines 596-612), but in a **different location** than the plan:

```python
# Actual implementation (lines 588-612):
for photo in photos:
    ad_image = AdImage.objects.create(
        ad_id=ad_id,
        image=photo["storage_key"],
        telegram_file_id=photo["telegram_file_id"],
        position=photo["position"],
    )
    # Generate thumbnails AFTER AdImage creation
    try:
        original_path = os.path.join(settings.MEDIA_ROOT, photo["storage_key"])
        with open(original_path, "rb") as f:
            photo_bytes = f.read()
        thumbnail_service = ThumbnailService(settings.MEDIA_ROOT)
        thumbnail_keys = thumbnail_service.generate_thumbnails(
            photo_bytes, photo["storage_key"]
        )
        ad_image.thumbnail_small = thumbnail_keys.get(ThumbnailSizeStrEnum.SMALL)
        ad_image.thumbnail_medium = thumbnail_keys.get(ThumbnailSizeStrEnum.MEDIUM)
        ad_image.thumbnail_large = thumbnail_keys.get(ThumbnailSizeStrEnum.LARGE)
        ad_image.save()
    except Exception:
        logger.exception("Failed to generate thumbnails for %s", photo["storage_key"])
```

**Key differences from plan:**
- **Timing:** Plan wanted thumbnails during `save_photo()` (upload time). Actual code generates them during `update_ad_and_moderate()` (moderation time).
- **Efficiency:** Actual code reads the photo file back from disk (`open(original_path, "rb")`) instead of using the in-memory bytes. The plan's approach would pass cleaned bytes directly.
- **AdImage creation:** Plan wanted thumbnail keys passed to `AdImage.objects.create()`. Actual code creates AdImage first, then updates it with `ad_image.save()`.
- **Graceful fallback:** Actual code wraps thumbnail generation in try/except, so AdImage is created even if thumbnails fail. The plan's `save_photo_with_thumbnails()` also had fallback but at the save level.

**Task YAML alignment:** The task file `TASK_055_Integrate_ThumbnailService_into_bot_DONE.yaml` (line 16) states: *"Generate thumbnails for each uploaded photo in update_ad_and_moderate."* This matches the actual implementation, confirming the deviation from the plan was intentional.

### T3.3: Add Model Fields — ✅ IMPLEMENTED

Same as T1.2. Fields exist in `AdImage` model (lines 361-378). No separate work needed.

---

## Phase 4: Backfill

### T4.1: Backfill Thumbnails Management Command — ❌ NOT IMPLEMENTED

**Plan anchor:** `src/backend/apps/media/management/commands/backfill_thumbnails.py`
**Actual state:** File does not exist. Only `__init__.py` is present in the `commands/` directory.

The `management/commands/` directory structure exists (T2.1 created it), but no `backfill_thumbnails.py` command was created. This means:
- No way to generate thumbnails for existing `AdImage` records that were created before thumbnail support.
- The backfill command is listed in research.md §10 (Files to Create) and plan.md §T4.1.

**Impact:** Existing ads (created before this feature) will never have thumbnails. The templates would fall back to `image_url` (if they were updated), but since templates are also not updated (T5.1/T5.2), this is currently a non-issue. However, if templates are later updated to use `thumbnail_small_url|default:image_url`, existing ads would correctly fall back to full-size images.

---

## Phase 5: Templates

### T5.1: Update Ad List Template — ❌ NOT IMPLEMENTED

**Plan anchor:** `src/backend/templates/ads/partials/ad_list.html`
**Actual file:** `src/backend/templates/ads/partials/ad_list.html` (117 lines)

Current code (line 29-33):
```html
<img 
    src="{{ ad.images.first.image_url }}" 
    alt="{{ ad|get_title:LANGUAGE_CODE }}"
    class="w-full h-48 object-cover rounded-t-lg"
>
```

Plan wanted:
```html
<img src="{{ ad.images.first.thumbnail_small_url|default:ad.images.first.image_url }}"
     alt="{{ ad.title }}"
     class="w-full h-48 object-cover rounded-t-lg"
     loading="lazy"
     width="240" height="180">
```

**Deviations:**
- Still uses `image_url` (full-size), not `thumbnail_small_url`.
- No `loading="lazy"` attribute.
- No `width`/`height` attributes.
- Uses `ad|get_title:LANGUAGE_CODE` (correct existing pattern) vs plan's `ad.title` (simplified).

### T5.2: Update Detail Template — ❌ NOT IMPLEMENTED

**Plan anchor:** `src/backend/templates/ads/detail.html`
**Actual file:** `src/backend/templates/ads/detail.html` (104 lines)

Current code (line 34-38):
```html
<img 
    src="{{ image.image_url }}" 
    alt="{% trans "Photo" %} {{ forloop.counter }} {% trans "for" %} {{ ad|get_title:LANGUAGE_CODE }}"
    class="w-full {% if ad.images.count == 1 %}max-h-96{% else %}h-64{% endif %} object-cover rounded-lg"
>
```

Plan wanted:
```html
<img src="{{ image.thumbnail_large_url|default:image.image_url }}"
     alt="Photo {{ forloop.counter }} for {{ ad.title }}"
     class="w-full {% if ad.images.count == 1 %}max-h-96{% else %}h-64{% endif %} object-cover rounded-lg"
     loading="lazy"
     width="1280" height="960">
```

**Deviations:**
- Still uses `image_url` (full-size), not `thumbnail_large_url`.
- No `loading="lazy"` attribute.
- No `width`/`height` attributes.

### T5.3: Register Media App — ✅ IMPLEMENTED

**Plan anchor:** `src/backend/config/settings/base.py`
**Actual location:** `base.py:100`

```python
"apps.media",
```

Registered in `INSTALLED_APPS` list. Verified correct.

---

## Additional Files to Modify (from plan "Files to Modify" table)

### `src/backend/apps/ads/views/listings.py` — ❌ `media_gate()` NOT extended

**Plan:** Extend `media_gate()` for thumbnail paths (research.md G10).
**Actual:** `media_gate()` (lines 87-151) only looks up `AdImage` by the `image` field:

```python
ad_image = AdImage.objects.select_related("ad").get(image=image_key)
```

**Critical issue:** If templates were updated to use `thumbnail_small_url` (which returns `media/<uuid>-small.jpg`), the `media_gate` would fail to find the AdImage because no record has `image` set to `<uuid>-small.jpg`. The thumbnail storage keys are stored in `thumbnail_small`, `thumbnail_medium`, `thumbnail_large` fields, not in `image`.

The research.md §3.3 (lines 140-177) describes extending `media_gate` to parse thumbnail keys and look up by the original key. This was not implemented.

### `src/backend/apps/ads/urls.py` — ❌ URL pattern NOT adjusted

**Plan:** Adjust media pattern to `<path:image_key>`.
**Actual:** `urls.py:31` uses `<str:image_key>`:

```python
path("media/<str:image_key>", media_gate, name="media_gate"),
```

The research.md §3.3 (line 176) recommends `<path:image_key>` to handle subdirectory paths like `thumbnails/small/<uuid>.jpg`. The current `<str:image_key>` converter does not match paths containing slashes.

**Note:** The actual implementation uses a flat storage pattern (`<uuid>-<size>.jpg`) rather than the subdirectory pattern (`thumbnails/<size>/<uuid>.jpg`) recommended in research.md §5. With the flat pattern, `<str:image_key>` works because keys don't contain slashes. However, the `media_gate` lookup issue (above) remains regardless of the URL converter.

---

## Research Fixes Compliance

The plan lists 8 "Key Research Findings (Required fixes)" in the overview (lines 17-26). Here is their implementation status:

| # | Fix | Status | Evidence |
|---|-----|--------|----------|
| 1 | Use `ThumbnailSizeStrEnum` (not `ThumbnailSize`) | ✅ | `enums.py:74`, imported in `thumbnails.py:15` and `ad_create.py:19` |
| 2 | Fix Task names to use AdImage naming | ✅ | Model class is `AdImage`; variable in `_update_and_moderate()` is `ad_image` |
| 3 | Fix constant to `Image.Resampling.LANCZOS` | ✅ | `thumbnails.py:23` — `RESAMPLING = Image.Resampling.LANCZOS` |
| 4 | Add quality=85 parameter | ✅ | `thumbnails.py:21` — `QUALITY = 85`; used in `save()` at line 86 |
| 5 | Add progressive JPEG support | ✅ | `thumbnails.py:24` — `PROGRESSIVE = True`; used at line 87 |
| 6 | Add background color for non-square images | ❌ | `thumbnail()` preserves aspect ratio without padding; no canvas/white-fill logic |
| 7 | Fix storage key to `<uuid>-<size>.jpg` pattern | ✅ | `thumbnails.py:75` — `key = f"{stem}-{size_enum.value}.jpg"` |
| 8 | Add cache-control headers guidance | ❌ | No cache-control headers in `media_gate()` or nginx config; research.md §2.2 G11 identifies this as a gap |

---

## Storage Layout Deviation

| Aspect | Research.md recommendation | Plan T2.2 code snippet | Actual implementation |
|--------|--------------------------|----------------------|----------------------|
| Layout | `thumbnails/{small,medium,large}/<uuid>.jpg` | `<uuid>-<size>.jpg` (flat) | `<uuid>-<size>.jpg` (flat) |
| Key pattern | `thumbnails/<variant>/<uuid>.jpg` | `<uuid>-<size>.jpg` | `<uuid>-<size>.jpg` |

The actual implementation follows the plan's T2.2 code snippet (flat pattern), not the research.md §5 recommendation (subdirectory pattern). This is a **plan-internal inconsistency** — the plan's code snippet (line 216) uses `f"{stem}-{size.value}.jpg"` (flat), while research.md §5 (line 377-383) recommends `thumbnails/{variant}/<uuid>.jpg` (subdirectory). The implementation chose the flat pattern, which is simpler and works with the existing `<str:image_key>` URL converter.

---

## Task YAML Files Review

Three task YAML files in `.ai/tasks/done/` confirm the implementation was tracked:

| Task ID | Title | Source Section | Status |
|---------|-------|---------------|--------|
| TASK_011 | Implement ThumbnailService with Pillow | T2.2 | ✅ Done |
| TASK_042 | Unit tests for ThumbnailService | T2.3 | ✅ Done |
| TASK_055 | Integrate ThumbnailService into bot | T3.2 | ✅ Done |

**Notable:** The task YAMLs do not cover T1.1, T1.2, T2.1, T3.1, T3.3, T4.1, T5.1, T5.2, T5.3, or the `media_gate`/`urls.py` changes. This suggests these tasks were either done without YAML tracking or were skipped.

---

## Rollout Analysis

### Risks

| Risk | Level | Assessment |
|------|-------|------------|
| Schema migration | MEDIUM | Fields are nullable; safe rollout. Migration numbered 0007 (not 0004) — cosmetic only. |
| Concurrent thumbnail generation | LOW | `O_CREAT \| O_EXCL` prevents race conditions. UUID-based naming avoids collisions. |
| Storage space increase | MEDIUM | Estimated 15-25% overhead for three thumbnail variants per image. |
| Image quality degradation | LOW | LANCZOS resampling, quality=85, progressive JPEG. |
| **Templates not updated** | **HIGH** | Thumbnails are generated but never served. Users see full-size images. Wasted storage. |
| **media_gate cannot serve thumbnails** | **HIGH** | Even if templates were updated, `media_gate` would 404 on thumbnail URLs. |
| **No backfill command** | MEDIUM | Existing ads never get thumbnails. New ads get thumbnails but they're not served (due to template issue). |
| Background color not implemented | LOW | Non-square thumbnails are smaller than target dimensions. CSS `object-fit: cover` compensates on client side. |

### Dependencies

The plan's execution DAG is mostly respected:
- T1.1 → T1.2 (enum before migration) ✅
- T2.1 → T2.2 (app structure before service) ✅
- T2.2 → T2.3 (service before tests) ✅
- T3.1 → T3.2 (URL properties before integration) ✅
- T2.1 → T5.3 (app structure before registration) ✅

### Backward Compatibility

- Thumbnail fields are nullable — existing code works without them.
- `save_photo()` is unchanged — existing photo upload flow is unaffected.
- `media_gate()` is unchanged — existing image serving works.
- Templates are unchanged — existing UI is unaffected.
- The only new code path is in `_update_and_moderate()` which wraps thumbnail generation in try/except with graceful fallback.

---

## Warnings

1. **Critical gap: Templates don't use thumbnails.** The entire thumbnail generation pipeline is functional but invisible to end users. The `thumbnail_small_url` and `thumbnail_large_url` properties exist but are never referenced in any template. This is the highest-priority gap.

2. **Critical gap: `media_gate()` cannot resolve thumbnail keys.** Even if templates were updated, `media_gate()` looks up `AdImage` only by the `image` field. Thumbnail URLs (`<uuid>-small.jpg`) would return 404 because no AdImage has `image` set to a thumbnail key. The `media_gate()` function needs to be extended to check `thumbnail_small`, `thumbnail_medium`, and `thumbnail_large` fields, or the URL pattern needs to be adjusted.

3. **No backfill command.** Existing `AdImage` records (created before this feature) will never have thumbnails. A management command is needed to iterate existing records and generate thumbnails.

4. **Background color handling missing.** Non-square images produce thumbnails smaller than the target dimensions (e.g., 240×135 instead of 240×180 for SMALL). This is compensated by CSS `object-fit: cover` in templates, but the plan's research fix #6 explicitly requires white background padding.

5. **Storage key pattern inconsistency.** The plan's T2.2 code snippet uses flat keys (`<uuid>-<size>.jpg`), but research.md §5 recommends subdirectory layout (`thumbnails/<size>/<uuid>.jpg`). The implementation chose the flat pattern, which is inconsistent with the research document.

6. **No `ThumbnailGenerationError` exception.** The plan specifies a custom exception class, but the implementation raises `ValueError` instead. This is a minor deviation.

7. **No logging in ThumbnailService.** The plan's code snippet imports `structlog`, but the implementation has no logging. Errors are only visible via the caller's try/except in `_update_and_moderate()`.

8. **Migration numbering.** The plan specifies `0004_adimage_thumbnails.py`, but the actual file is `0007_adimage_thumbnails.py`. This is because other migrations were added in between. Not a functional issue.

---

## Required Fixes

1. **T5.1:** Update `ad_list.html` to use `thumbnail_small_url|default:image_url` with `loading="lazy"`, `width="240"`, `height="180"`.
2. **T5.2:** Update `detail.html` to use `thumbnail_large_url|default:image_url` with `loading="lazy"`, `width="1280"`, `height="960"`.
3. **media_gate():** Extend `media_gate()` in `listings.py` to look up AdImage by thumbnail fields when the `image_key` matches a thumbnail pattern (e.g., ends with `-small.jpg`, `-medium.jpg`, `-large.jpg`).
4. **T4.1:** Create `backfill_thumbnails.py` management command to generate thumbnails for existing AdImage records.

---

## Advisory Recommendations

1. **Background color handling:** Implement white background canvas padding in `ThumbnailService.generate_thumbnails()` to match research fix #6 and the plan's T2.2 code snippet. Update `test_aspect_ratio_preservation` to assert exact dimensions after padding.

2. **Storage key pattern:** Consider migrating to the research.md §5 recommended subdirectory layout (`thumbnails/{size}/<uuid>.jpg`) for cleaner organization and nginx `Cache-Control` header support. This would require updating `media_gate()`, URL patterns, and the backfill command.

3. **`ThumbnailGenerationError`:** Add the custom exception class to `thumbnails.py` for better error handling granularity.

4. **Logging:** Add `logging.getLogger(__name__)` to `thumbnails.py` for observability of thumbnail generation failures.

5. **Integration approach:** Consider moving thumbnail generation from `_update_and_moderate()` back to `save_photo()` (as the plan originally intended) to avoid the extra disk read. The plan's `save_photo_with_thumbnails()` approach is more efficient.

6. **`_atomic_write` helper:** Extract the atomic write logic into a separate method for testability and code organization, matching the plan's T2.2 specification.

7. **Cache-Control headers:** Add `Cache-Control: public, max-age=31536000, immutable` headers in `media_gate()` for thumbnail responses, as recommended in research.md §2.2 (G11).

---

## Summary Table

| Task | Plan Section | Status | File(s) | Notes |
|------|-------------|--------|---------|-------|
| T1.1 | Phase 1 | ✅ | `enums.py:74` | Exact match |
| T1.2 | Phase 1 | ✅ | `migrations/0007_*.py` | Numbered 0007 not 0004 |
| T2.1 | Phase 2 | ✅ | `apps/media/` | All dirs/files present |
| T2.2 | Phase 2 | ⚠️ | `services/thumbnails.py` | Missing: background padding, `ThumbnailGenerationError`, logging, `_atomic_write` helper. API is instance-based not static. |
| T2.3 | Phase 2 | ✅ | `tests/test_thumbnails.py` | Missing: background color test, atomic write test |
| T3.1 | Phase 3 | ✅ | `models.py:392-408` | Exact match |
| T3.2 | Phase 3 | ⚠️ | `ad_create.py` | `save_photo_with_thumbnails()` not created. Thumbnails generated in `_update_and_moderate()` instead. |
| T3.3 | Phase 3 | ✅ | `models.py:361-378` | Same as T1.2 |
| T4.1 | Phase 4 | ❌ | — | `backfill_thumbnails.py` does not exist |
| T5.1 | Phase 5 | ❌ | `ad_list.html` | Still uses `image_url` |
| T5.2 | Phase 5 | ❌ | `detail.html` | Still uses `image_url` |
| T5.3 | Phase 5 | ✅ | `base.py:100` | Exact match |
| — | Files to Modify | ❌ | `listings.py` | `media_gate()` not extended for thumbnails |
| — | Files to Modify | ❌ | `urls.py` | Still `<str:image_key>`, not `<path:image_key>` |
