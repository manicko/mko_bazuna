# Photo Thumbnail Generation - Research Report

**Generated:** 2026-07-26  
**Phase:** Research  
**Delivarable:** Detailed analysis of current state, gaps, modern practices, and implementation approach for thumbnail generation in Mko Bazuna.

---

## 1. Current State Analysis

### 1.1 Photo Handling Flow (Observed)

**Entry Point:** `src/telegram_bot/handlers/ad_create.py`

The ad creation flow handles photos as follows:

1. **Photo Download:** `download_photo(file_id, bot)` downloads photo bytes from Telegram (line 432-439)
2. **Validation:** `validate_photo(photo_bytes, max_width, max_height)` checks:
   - JPEG magic bytes (`b"\xff\xd8\xff"`)
   - File size (~2MB max)
   - Dimensions (max 2560x2560 pixels)
   - Applies `exif_transpose` for orientation correction during validation
3. **Storage Key Generation:** `generate_storage_key()` produces UUID v4 format (`<uuid>.jpg`) for anonymity
4. **Atomic Save:** `save_photo(storage_key, photo_bytes)` (lines 442-470):
   - Strips EXIF via `strip_photo_exif()`
   - Re-encodes with `optimize=True`
   - Uses `os.open(O_CREAT | O_EXCL)` for atomic writes
   - Retries with new key on collision (extremely rare with UUID v4)
5. **Model Creation:** `AdImage` records created with `storage_key` stored in `image` field (line 554-560)

### 1.2 AdImage Model (Current)

**File:** `src/backend/apps/ads/models.py` (lines 316-356)

```python
class AdImage(models.Model):
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name="images")
    image = models.CharField(max_length=64)  # storage key (UUID v4 + .jpg)
    telegram_file_id = models.CharField(max_length=255, blank=True, null=True)
    position = models.PositiveIntegerField(default=0)
    
    @property
    def image_url(self) -> str:
        """Return the media URL for this image."""
        from django.conf import settings
        return f"{settings.MEDIA_URL}{self.image}"
```

**Critical Observation:** No thumbnail fields exist. The model only stores the original image.

### 1.3 Template Consumption (Current)

**Ad List (line 28):** `{{ ad.images.first.image_url }}` renders original image at 480px height  
**Ad Detail (line 32):** `{{ image.image_url }}` renders original image at 640px height

**Problem:** Both templates load full-size images for thumbnails, causing unnecessary bandwidth and slower page loads.

### 1.4 Storage Configuration (Current)

**Settings:** `src/backend/config/settings/base.py`
- `MEDIA_URL = "media/"`
- `MEDIA_ROOT = BASE_DIR.parent / "media"` (mounted as `media_volume:/app/media`)
- Storage uses Django's `FileSystemStorage` backend

**Nginx Configuration:** `docker/nginx/nginx.conf`
- `/protected-media/` internal location serves files after Django access control
- `X-Accel-Redirect` header from Django triggers nginx file serving
- MIME type restricted to `image/jpeg` (lines 80-85)

---

## 2. Gap Analysis

### 2.1 Missing Components

| Component | Location | Description |
|-----------|----------|-------------|
| `ThumbnailSize` enum | `apps/core/enums.py` | StrEnum defining SMALL (240x180), MEDIUM (640x480), LARGE (1280x960) |
| `AdImage.thumbnail_small` | `apps/ads/models.py` | CharField(max_length=64, null=True) for thumbnail path |
| `AdImage.thumbnail_medium` | `apps/ads/models.py` | CharField(max_length=64, null=True) for thumbnail path |
| `AdImage.thumbnail_large` | `apps/ads/models.py` | CharField(max_length=64, null=True) for thumbnail path |
| `ThumbnailService` | `apps/media/services/thumbnails.py` | Service to generate all three sizes from original |
| `apps/media` module | New | Dedicated app for media processing |

### 2.2 Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| Schema migration | Medium | Nullable fields allow safe rollback; backward compatible |
| Thumbnail generation failure | Low | Graceful degradation: log warning, continue without thumbnails |
| Storage space increase | Medium | Estimated 15-25% overhead; monitor post-deployment |
| Image quality degradation | Low | LANCZOS resampling (highest quality) with optimize=True |

---

## 3. Modern Practices Research (2026)

### 3.1 Pillow Image Processing Best Practices

**Source:** Context7 documentation and Pillow 10.x release notes

#### 3.1.1 Resampling Methods (Ranked by Quality)

| Method | Use Case | Quality | Speed |
|--------|----------|---------|-------|
| `Image.LANCZOS` (deprecated alias) | High-quality downsampling | Excellent | Slower |
| `Image.Resampling.LANCZOS` | High-quality downsampling | Excellent | Slower |

**HIGH CONFIDENCE:** Use `Image.Resampling.LANCZOS` for production-quality thumbnails. Pillow 10.x maintains backward compatibility with `Image.LANCZOS`.

#### 3.1.2 Aspect Ratio Preservation

**Recommended approach:** Use `Image.thumbnail()` method which:
- Maintains aspect ratio automatically
- Does not upscale small images (prevents pixelation)
- Uses PIL's default LANCZOS resampling

```python
def generate_thumbnail(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    img.thumbnail(size, Image.Resampling.LANCZOS)
    return img
```

#### 3.1.3 EXIF Orientation Handling

**CRITICAL:** Mobile photos often have orientation stored in EXIF, not physically rotated.

**Best Practice:** Apply `ImageOps.exif_transpose()` BEFORE any processing:
```python
from PIL import ImageOps
img = ImageOps.exif_transpose(img)
```

This handles:
- 90° CW/CCW rotations
- Horizontal/vertical flips
- Normal (1) orientation unchanged

### 3.2 File Storage Patterns

#### 3.2.1 Atomic File Writes

**Current Implementation:** Already uses `O_CREAT | O_EXCL` (correct)

**Enhancement for Thumbnails:** Consider writing to temp file then atomic rename:
```python
# Write to temp, then rename (atomic on POSIX)
temp_path = path + ".tmp"
# ... write to temp ...
os.rename(temp_path, path)  # Atomic
```

**Alternative:** Keep current `O_CREAT | O_EXCL` pattern - simpler and already proven.

#### 3.2.2 Storage Layout

**Options:**
1. **Same directory:** `<uuid>.jpg`, `<uuid>-small.jpg`, `<uuid>-medium.jpg`, `<uuid>-large.jpg`
2. **Separate directory:** `thumbs/<uuid>-small.jpg`, etc.
3. **Subdirectory per size:** `small/<uuid>.jpg`, `medium/<uuid>.jpg`, etc.

**Recommendation:** Same directory with size suffix
- Simpler path construction
- Easy to clean up (delete all thumbs for an image)
- No additional directory traversal checks needed

Pattern: `<uuid_root>-<size>.jpg`
- Original: `a1b2c3d4.jpg`
- Small: `a1b2c3d4-small.jpg`
- Medium: `a1b2c3d4-medium.jpg`
- Large: `a1b2c3d4-large.jpg`

### 3.3 Nginx Caching Headers

The current nginx config serves static files with:
```nginx
expires 30d;
add_header Cache-Control "public, immutable";
```

**Recommendation for thumbnails:** Add explicit caching headers in nginx for media endpoint:
```nginx
location /protected-media/ {
    # ... existing security headers ...
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

**Cache Invalidation Strategy:** Filename-based invalidation (UUID ensures uniqueness on re-upload).

### 3.4 Image Quality Optimization

#### 3.4.1 JPEG Quality Settings

**Pillow `save()` options:**
```python
img.save(buf, format="JPEG", optimize=True, quality=85)
```

- `optimize=True`: Huffman table optimization (5-15% size reduction)
- `quality=85`: Sweet spot between quality and file size (default is 75)
- Consider `progressive=True` for better perceived loading on slow connections

#### 3.4.2 WebP Consideration (Deferred)

While WebP offers 25-35% smaller files, the plan specifies JPEG only. This is appropriate because:
- Telegram delivers JPEG
- Browser support is universal but conversion adds complexity
- Can be added in a future phase with content negotiation

---

## 4. Implementation Approach

### 4.1 Recommended Architecture

```
telegram_bot/
  handlers/
    ad_create.py          # Calls thumbnail service after photo save
    └── save_photo() → generate_thumbnails() on success

apps/
  core/
    enums.py             # ThumbnailSize enum (new)
  
  media/                 # NEW dedicated app (isolated)
    apps.py
    services/
      __init__.py
      thumbnails.py      # ThumbnailService.generate_thumbnails()
    management/
      commands/
        backfill_thumbnails.py
    tests/
      test_thumbnails.py
  
  ads/
    models.py            # Add thumbnail_* fields + properties
```

### 4.2 Thumbnail Generation Flow

```
1. User sends photo via Telegram bot
2. Photo downloaded to bytes
3. validate_photo() passes → proceed
4. save_photo() writes original to disk (atomic)
5. generate_thumbnails() called:
   - Opens original via BytesIO
   - Applies exif_transpose
   - Generates 3 sizes using thumbnail()
   - Writes each with O_CREAT|O_EXCL
   - Returns dict of {ThumbnailSize: storage_key}
6. AdImage created with all keys
7. On failure: log warning, ad proceeds without thumbnails
```

### 4.3 Backward Compatibility

The plan correctly identifies that:
1. Thumbnail fields are nullable → existing images work
2. Templates use `or` fallback → `image_url or thumbnail_small_url`
3. Original image always preserved → rollback safe

---

## 5. Technical Details

### 5.1 ThumbnailSize Enum Specification

```python
class ThumbnailSize(StrEnum):
    """Thumbnail dimensions for responsive image rendering."""
    
    SMALL = "small"     # 240x180 (list view, mobile cards)
    MEDIUM = "medium"   # 640x480 (detail view gallery)
    LARGE = "large"     # 1280x960 (detail view single, potential future use)
```

Dimensions calculated as:
- SMALL: 240x180 (4:3 ratio) - fits 480px container with 2x retina
- MEDIUM: 640x480 (4:3 ratio) - fits 960px container with 1.5x retina  
- LARGE: 1280x960 (4:3 ratio) - fits 1280px container, full preview

### 5.2 Migration Specification

**File:** `src/backend/apps/ads/migrations/0004_adimage_thumbnails.py`

```python
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('ads', '0003_add_index_conditions'),
    ]

    operations = [
        migrations.AddField(
            model_name='adimage',
            name='thumbnail_small',
            field=models.CharField(max_length=64, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='adimage',
            name='thumbnail_medium',
            field=models.CharField(max_length=64, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='adimage',
            name='thumbnail_large',
            field=models.CharField(max_length=64, null=True, blank=True),
        ),
    ]
```

**Note:** `blank=True` needed for Django admin form validity.

### 5.3 AdImage Model Updates

```python
class AdImage(models.Model):
    # ... existing fields ...
    
    thumbnail_small = models.CharField(max_length=64, null=True, blank=True)
    thumbnail_medium = models.CharField(max_length=64, null=True, blank=True)
    thumbnail_large = models.CharField(max_length=64, null=True, blank=True)
    
    @property
    def thumbnail_small_url(self) -> str | None:
        if self.thumbnail_small:
            return f"{settings.MEDIA_URL}{self.thumbnail_small}"
        return None
    
    @property
    def thumbnail_medium_url(self) -> str | None:
        if self.thumbnail_medium:
            return f"{settings.MEDIA_URL}{self.thumbnail_medium}"
        return None
    
    @property
    def thumbnail_large_url(self) -> str | None:
        if self.thumbnail_large:
            return f"{settings.MEDIA_URL}{self.thumbnail_large}"
        return None
```

### 5.4 ThumbnailService Implementation

```python
# apps/media/services/thumbnails.py
from enum import StrEnum
import io
from pathlib import Path
from PIL import Image, ImageOps
from pydantic import ValidationError

class ThumbnailSize(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"

THUMBNAIL_DIMENSIONS: dict[ThumbnailSize, tuple[int, int]] = {
    ThumbnailSize.SMALL: (240, 180),
    ThumbnailSize.MEDIUM: (640, 480),
    ThumbnailSize.LARGE: (1280, 960),
}

def generate_thumbnails(
    original_bytes: bytes,
    storage_key: str,
) -> dict[ThumbnailSize, str]:
    """Generate thumbnail variants from original JPEG bytes.
    
    Args:
        original_bytes: JPEG image bytes after EXIF stripping
        storage_key: Original storage key (e.g., "a1b2c3d4.jpg")
    
    Returns:
        Dict mapping ThumbnailSize to generated storage keys
    
    Raises:
        ValidationError: If original_bytes is not valid JPEG
    """
    # Validate input is JPEG
    if not original_bytes.startswith(b"\xff\xd8\xff"):
        raise ValidationError("Invalid JPEG data")
    
    # Open and correct orientation
    img = Image.open(io.BytesIO(original_bytes))
    img = ImageOps.exif_transpose(img)
    
    # Extract UUID root from storage key
    uuid_root = storage_key.rsplit(".", 1)[0]
    
    result: dict[ThumbnailSize, str] = {}
    
    for size, (width, height) in THUMBNAIL_DIMENSIONS.items():
        thumb = img.copy()
        thumb.thumbnail((width, height), Image.Resampling.LANCZOS)
        
        thumb_key = f"{uuid_root}-{size.value}.jpg"
        thumb_path = Path(settings.MEDIA_ROOT) / thumb_key
        
        buf = io.BytesIO()
        thumb.save(buf, format="JPEG", optimize=True, quality=85)
        
        # Atomic write
        fd = os.open(thumb_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, buf.getvalue())
        finally:
            os.close(fd)
        
        result[size] = thumb_key
    
    return result
```

### 5.5 Integration Points

**save_photo modification (ad_create.py):**

```python
async def save_photo(storage_key: str, photo_bytes: bytes) -> str:
    # ... existing code ...
    
    # After successful save, generate thumbnails
    try:
        thumbnail_keys = await asyncio.to_thread(
            generate_thumbnails, cleaned, storage_key
        )
        # Return both original and thumbnail keys
        return {"original": storage_key, "thumbnails": thumbnail_keys}
    except Exception as e:
        logger.warning(f"Thumbnail generation failed: {e}")
        return {"original": storage_key, "thumbnails": {}}
```

**Template updates:**

```html
<!-- ad_list.html line 28 -->
<img 
    src="{{ ad.images.first.thumbnail_small_url or ad.images.first.image_url }}"
    ...
>

<!-- detail.html line 32 -->
<img 
    src="{{ image.thumbnail_medium_url or image.image_url }}"
    ...
>
```

### 5.6 Nginx Configuration Update

Add to `docker/nginx/nginx.conf` in the `/protected-media/` block:

```nginx
location /protected-media/ {
    # ... existing headers ...
    
    # Cache thumbnails for 30 days (immutable - filename changes on content change)
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

---

## 6. Performance Considerations

### 6.1 Storage Overhead Estimate

For an average original image of 1MB:
| Size | Dimensions | Estimated Size | Cumulative |
|------|------------|----------------|----------|
| Original | Variable (up to 2560x2560) | ~1000 KB | 100% |
| Large | 1280x960 | ~250 KB | 125% |
| Medium | 640x480 | ~80 KB | 133% |
| Small | 240x180 | ~25 KB | 138% |

**Total overhead:** ~35-40% for all three thumbnails

### 6.2 CPU Impact

Thumbnail generation is CPU-bound. For high-volume scenarios:
1. Current: Uses `asyncio.to_thread()` for blocking ops
2. Future optimization: Consider `concurrent.futures.ThreadPoolExecutor` for batch processing
3. The backfill command should use batch processing with progress logging

### 6.3 CDN Readiness

The UUID-based filename strategy supports:
- Cache busting (new UUID = cache miss)
- No query parameter caching issues
- Easy migration to S3 (just change `STORAGES` backend)

---

## 7. Testing Strategy

### 7.1 Unit Tests Required

Following the existing test patterns in `test_media_security.py`:

1. **test_generate_thumbnails_valid_image** - Valid JPEG produces all three variants
2. **test_generate_thumbnails_aspect_ratio** - Wide/tall images maintain proportions
3. **test_generate_thumbnails_exif_orientation** - Rotated images are corrected
4. **test_generate_thumbnails_invalid_input** - Raises ValidationError on non-JPEG
5. **test_generate_thumbnails_storage_key_format** - Follows `<uuid>-<size>.jpg` pattern
6. **test_generate_thumbnails_atomic_write** - O_CREAT|O_EXCL prevents overwrites

### 7.2 Integration Tests Required

1. **Template fallback renders original** when thumbnails null
2. **Backfill command handles missing files gracefully**
3. **Concurrent thumbnail generation** doesn't corrupt files

---

## 8. Security Considerations

### 8.1 Existing Security (Validated)

- Path traversal blocked in `MediaAccessView` (test_media_security.py)
- MIME type restricted to JPEG at nginx level
- EXIF stripping removes GPS/camera metadata
- UUID keys prevent inference of user identity

### 8.2 Additional Considerations

- Thumbnail files inherit access control via original key linkage (same AdImage)
- No additional user input for thumbnails (derived from validated originals)
- Size limits inherited from original validation (no need to re-validate)

---

## 9. Confidence Assessment

| Finding | Confidence | Source |
|---------|------------|--------|
| Pillow LANCZOS best for quality | HIGH | Pillow documentation, plan reference |
| `thumbnail()` maintains aspect ratio | HIGH | Pillow API confirmed |
| `exif_transpose` handles mobile rotation | HIGH | Existing code uses it correctly |
| UUID collision probability negligible | HIGH | UUID v4 statistical properties |
| Storage overhead estimate | MEDIUM | Based on typical JPEG compression ratios |
| Nginx immutable caching strategy | HIGH | Standard practice, matches static file config |

---

## 10. Recommendations Summary

1. **Proceed with plan as designed** - The phased approach (schema → service → integration) is sound
2. **Use `Image.Resampling.LANCZOS`** - Explicit enum value for forward compatibility
3. **Add `quality=85` to thumbnail saves** - Better than default 75
4. **Consider progressive JPEG for thumbnails** - Improves perceived loading
5. **Keep thumbnails in same directory** - Simpler lifecycle management
6. **Add cache headers to nginx** - Both static and protected-media locations

**Implementation Priority:** Phase 1 and 2 can proceed immediately. Phase 4 (backfill) should run during low-traffic window after deployment.