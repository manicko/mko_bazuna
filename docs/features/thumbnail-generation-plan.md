---
id: thumbnail-generation-plan
domain: features
tags:
  - thumbnails
  - images
  - media
related:
  - db-schema
  - architecture
---

## Purpose

Implementation plan for Photo Thumbnail Generation enhancement. Adds thumbnail variants (small/medium/large) to existing image storage pipeline.

## Main Concepts

- **Thumbnail sizes:** Small (240x180), Medium (640x480), Large (1280x960) - all landscape orientation with aspect-ratio preservation
- **Storage:** Thumbnails stored alongside original images in MEDIA_ROOT using UUID-based naming
- **Integration point:** `update_ad_and_moderate()` in `telegram_bot/handlers/ad_create.py` triggers thumbnail generation
- **Backfill:** Management command generates thumbnails for existing images

## Risk Assessment

| Factor | Assessment | Mitigation |
|--------|------------|------------|
| Schema migration | Medium | Uses additive nullable fields; safe for existing data |
| Concurrent thumbnail generation | Low | Uses atomic file writes with O_EXCL |
| Storage space increase | Medium | ~15% overhead for three resized variants |
| File system race conditions | Low | O_EXCL guarantees atomic creation |

## Execution DAG

```
Phase 1: Schema & Constants
  ├─ Task 1.1: Create ThumbnailSize StrEnum
  └─ Task 1.2: Migration for AdImage.thumbnail_small/medium/large

Phase 2: Service Layer
  ├─ Task 2.1: Create apps/media/services/thumbnails.py
  ├─ Task 2.2: Implement generate_thumbnails() method
  └─ Task 2.3: Unit tests for thumbnail generation

Phase 3: Integration
  ├─ Task 3.1: Update save_photo to generate thumbnails
  ├─ Task 3.2: Update AdImage model with URL properties
  └─ Task 3.3: Add thumbnail_url properties

Phase 4: Backfill
  └─ Task 4.1: Management command for existing images

Phase 5: Templates
  ├─ Task 5.1: Update ad_list.html to use thumbnails
  └─ Task 5.2: Update detail.html for gallery thumbnails
```

## Task Specifications

### Task 1.1: Create ThumbnailSize StrEnum

**Semantic Anchor:** `apps.core.enums.ThumbnailSize`

**Description:** Define thumbnail size variants as StrEnum for type-safe size constants.

**Dependencies:** None

**Files:**
- `src/backend/apps/core/enums.py` (add new enum)

**Implementation:**
```python
class ThumbnailSize(StrEnum):
    SMALL = "small"   # 240x180
    MEDIUM = "medium"  # 640x480
    LARGE = "large"   # 1280x960
```

---

### Task 1.2: Migration for AdImage Thumbnail Fields

**Semantic Anchor:** `apps.ads.migrations.0004_adimage_thumbnails`

**Description:** Add nullable thumbnail fields to AdImage model.

**Dependencies:** Task 1.1

**Files:**
- `src/backend/apps/ads/migrations/0004_adimage_thumbnails.py`

**Fields to add:**
- `thumbnail_small: CharField(max_length=64, null=True, blank=True)`
- `thumbnail_medium: CharField(max_length=64, null=True, blank=True)`  
- `thumbnail_large: CharField(max_length=64, null=True, blank=True)`

---

### Task 2.1: Create ThumbnailService Module

**Semantic Anchor:** `apps.media.services.thumbnails.ThumbnailService`

**Description:** Create new media service module for thumbnail generation.

**Dependencies:** Task 1.1

**Files:**
- `src/backend/apps/media/__init__.py` (new)
- `src/backend/apps/media/apps.py` (new)
- `src/backend/apps/media/services/__init__.py` (new)

---

### Task 2.2: Implement generate_thumbnails()

**Semantic Anchor:** `apps.media.services.thumbnails.ThumbnailService.generate_thumbnails`

**Description:** Generate three thumbnail variants from original image bytes.

**Dependencies:** Task 2.1

**Files:**
- `src/backend/apps/media/services/thumbnails.py` (new)

**Implementation Details:**
```python
def generate_thumbnails(
    original_bytes: bytes,
    original_key: str,
) -> dict[ThumbnailSize, str]:
    """Generate thumbnail keys and save to MEDIA_ROOT.
    
    Args:
        original_bytes: Raw JPEG bytes
        original_key: Storage key of original image (e.g., "<uuid>.jpg")
        
    Returns:
        Dict mapping ThumbnailSize to storage key for each variant
    """
```

**Behavior:**
- Uses Pillow for image resizing with `Image.LANCZOS` resampling
- Maintains aspect ratio, crops to exact dimensions if needed
- Uses `exif_transpose` for orientation correction
- Atomic file writes with `O_CREAT | O_EXCL`
- Returns storage keys (e.g., `<uuid>-small.jpg`, `<uuid>-medium.jpg`, `<uuid>-large.jpg`)

---

### Task 2.3: Unit Tests for Thumbnail Generation

**Semantic Anchor:** `apps.media.tests.test_thumbnails`

**Description:** Test thumbnail generation with various image sizes.

**Dependencies:** Task 2.2

**Files:**
- `src/backend/apps/media/tests/__init__.py` (new)
- `src/backend/apps/media/tests/test_thumbnails.py` (new)

**Test Cases:**
- Valid small image generates all three variants
- Large original image resizes correctly (bounds check)
- EXIF orientation handled correctly
- Invalid image bytes raise appropriate error
- Storage keys follow UUID naming pattern

---

### Task 3.1: Update save_photo Integration

**Semantic Anchor:** `telegram_bot.handlers.ad_create.save_photo`

**Description:** Integrate thumbnail generation into photo save flow.

**Dependencies:** Task 2.2

**Files:**
- `src/telegram_bot/handlers/ad_create.py`

**Changes:**
- Modify `save_photo()` to call `generate_thumbnails()` after original save
- Generate thumbnails from cleaned EXIF-stripped bytes
- Handle thumbnail generation failures gracefully (log warning, don't fail ad creation)

---

### Task 3.2: Update AdImage Model

**Semantic Anchor:** `apps.ads.models.AdImage.thumbnail_urls`

**Description:** Add URL properties for thumbnail variants.

**Dependencies:** Task 2.1

**Files:**
- `src/backend/apps/ads/models.py`

**Properties to add:**
```python
@property
def thumbnail_small_url(self) -> str | None:
    if self.thumbnail_small:
        return f"{settings.MEDIA_URL}{self.thumbnail_small}"

@property  
def thumbnail_medium_url(self) -> str | None:
    if self.thumbnail_medium:
        return f"{settings.MEDIA_URL}{self.thumbnail_medium}"

@property
def thumbnail_large_url(self) -> str | None:
    if self.thumbnail_large:
        return f"{settings.MEDIA_URL}{self.thumbnail_large}"
```

---

### Task 4.1: Backfill Management Command

**Semantic Anchor:** `apps.media.management.commands.backfill_thumbnails`

**Description:** Generate thumbnails for all existing AdImage records.

**Dependencies:** Task 2.2, Task 3.2

**Files:**
- `src/backend/apps/media/management/__init__.py` (new)
- `src/backend/apps/media/management/commands/__init__.py` (new)
- `src/backend/apps/media/management/commands/backfill_thumbnails.py` (new)

**Implementation:**
- Iterate all AdImage with non-null `image` field
- Skip images that already have thumbnails
- Log progress and summary statistics
- Handle file-not-found gracefully (skip and log warning)

---

### Task 5.1: Update Ad List Template

**Semantic Anchor:** `templates.ads.partials.ad_list`

**Description:** Use thumbnail_small_url in ad cards grid.

**Dependencies:** Task 3.2

**Files:**
- `src/backend/templates/ads/partials/ad_list.html`

**Changes:**
- Replace `ad.images.first.image_url` with `ad.images.first.thumbnail_small_url or ad.images.first.image_url`
- Maintains fallback to original image for backward compatibility

---

### Task 5.2: Update Detail Template

**Semantic Anchor:** `templates.ads.detail`

**Description:** Use thumbnail_medium_url in detail page gallery.

**Dependencies:** Task 3.2

**Files:**
- `src/backend/templates/ads/detail.html`

**Changes:**
- Replace `image.image_url` with `image.thumbnail_medium_url or image.image_url`
- Maintains responsive sizing with h-64/h-96 classes

---

## Migration Order

1. Deploy Task 1.1 (enum) and Task 1.2 (migration)
2. Deploy Task 2.1-2.3 (thumbnail service + tests)
3. Deploy Task 3.1-3.2 (integration)
4. Run Task 4.1 backfill after deployment
5. Deploy Task 5.1-5.2 (templates)

## Rollback Plan

If issues arise:
1. Revert templates to use `image_url` (original images)
2. Original images remain untouched
3. Thumbnail fields nullable - rollback safe