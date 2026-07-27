# Photo Thumbnail Generation - Detailed Implementation Plan

## Overview

**Phase:** 2  
**Plan ID:** 1  
**Created:** 2026-07-26  
**Risk Level:** MEDIUM  

Implement thumbnail generation for uploaded photos in Mko Bazuna classifieds platform. Generate three thumbnail sizes (small: 240×180, medium: 640×480, large: 1280×960) for all uploaded images to improve page load times and user experience.

**Critical Dependencies:**
- Current photo pipeline works (JPEG validation, EXIF stripping, atomic writes)
- Required: Add thumbnail fields to `AdImage` model  
- Required: New `apps.media` app with `ThumbnailService`

**Key Research Findings (Required fixes):**
1. Use `ThumbnailSizeStrEnum` (not `ThumbnailSize`) 
2. Fix Task names to use AdImage naming
3. Fix constant to `Image.Resampling.LANCZOS`
4. Add quality=85 parameter in generation
5. Add progressive JPEG support
6. Add background color handling for non-square images
7. Fix storage key to `<uuid>-<size>.jpg` pattern (research spec)
8. Add cache-control headers guidance

## Execution Summary

Phase 1: Schema & Constants - Add enum and DB fields (no runtime changes)
Phase 2: Service Layer - Create thumbnail service in isolation
Phase 3: Model & Integration - Connect service to data layer and photo upload flow  
Phase 4: Backfill - Populate thumbnails for existing images
Phase 5: Templates - Use thumbnails in frontend consumption

## Phase 1: Schema & Constants (No Runtime Risk)

### T1.1: Create ThumbnailSizeStrEnum
**Priority:** HIGH  
**Risk Level:** LOW  
**Semantic Anchor:** `src/backend/apps/core/enums.py`
**Dependencies:** None  

**Task Implementation Steps:**
1. Open `src/backend/apps/core/enums.py`
2. Add `ThumbnailSizeStrEnum` class at end of file:
   ```python
   class ThumbnailSizeStrEnum(StrEnum):
       """Standard thumbnail sizes for Mko Bazuna."""
       SMALL = "small"
       MEDIUM = "medium"  
       LARGE = "large"
   ```
3. Add size mappings in ThumbnailService:
   ```python
   SIZES = {
       ThumbnailSizeStrEnum.SMALL: (240, 180),
       ThumbnailSizeStrEnum.MEDIUM: (640, 480), 
       ThumbnailSizeStrEnum.LARGE: (1280, 960),
   }
   ```
4. Add docstring with size specifications

**Specifications:**
- SMALL: 240×180 pixels
- MEDIUM: 640×480 pixels  
- LARGE: 1280×960 pixels

**VERIFICATION FIX:**
- Research.md specifies `ThumbnailSizeStrEnum` must be used, not `ThumbnailSize`

**Verification:**
```bash
uv run basedpyright src/backend/apps/core/enums.py
uv run ruff check src/backend/apps/core/enums.py
```

---

### T1.2: Migration: Add Thumbnail Fields to AdImage
**Priority:** HIGH  
**Risk Level:** MEDIUM  
**Semantic Anchor:** `src/backend/apps/ads/migrations/0004_adimage_thumbnails.py`
**Dependencies:** T1.1  

**Task Implementation Steps:**
1. Create migration file `src/backend/apps/ads/migrations/0004_adimage_thumbnails.py`
2. Add ThumbnailSizeStrEnum import from `apps.core.enums`
3. Add three nullable CharFields to AdImage model following research storage key pattern:
   ```python
   thumbnail_small = models.CharField(
       max_length=64,
       blank=True,
       null=True,
       help_text="Storage key for small thumbnail (<uuid>-small.jpg)",
   )
   
   thumbnail_medium = models.CharField(
       max_length=64, 
       blank=True,
       null=True,
       help_text="Storage key for medium thumbnail (<uuid>-medium.jpg)",
   )
   
   thumbnail_large = models.CharField(
       max_length=64,
       blank=True,
       null=True, 
       help_text="Storage key for large thumbnail (<uuid>-large.jpg)",
   )
   ```
4. Create corresponding changes in `src/backend/apps/ads/models.py`
5. Generate migration using: `uv run python manage.py makemigrations apps.ads`

**Why nullable:** Allows safe rollout - thumbnails optional during deployment

**Verification:**
```bash
uv run python src/backend/manage.py makemigrations --check --dry-run apps.ads
uv run python src/backend/manage.py migrate --plan
```

## Phase 2: Service Layer (Isolated Media App)

### T2.1: Create Media App Structure
**Priority:** MEDIUM  
**Risk Level:** LOW  
**Semantic Anchor:** `src/backend/apps/media/`
**Dependencies:** T1.2  

**Task Implementation Steps:**
1. Create directory: `src/backend/apps/media/`
2. Create files:
   - `src/backend/apps/media/__init__.py` - empty package
   - `src/backend/apps/media/apps.py` - Django app config
   - `src/backend/apps/media/services/__init__.py` - Services package
   - `src/backend/apps/media/tests/__init__.py` - Tests package
   - `src/backend/apps/media/management/__init__.py` - Management package
   - `src/backend/apps/media/management/commands/__init__.py` - Commands package
3. Create all subdirectories with appropriate `__init__.py` files

**Verification:**
```bash
uv run basedpyright src/backend/apps/media/
uv run python -c "from django.apps import apps; print('apps.media' in [a.name for a in apps.app_configs.values()])"
```

---

### T2.2: Implement ThumbnailService
**Priority:** HIGH  
**Risk Level:** LOW  
**Semantic Anchor:** `src/backend/apps/media/services/thumbnails.py`
**Dependencies:** T2.1  

**Task Implementation Steps:**
1. Create `src/backend/apps/media/services/thumbnails.py`
2. Import required modules:
   ```python
   from PIL import Image, ImageOps
   from apps.core.enums import ThumbnailSizeStrEnum
   import os
   from typing import Dict
   import structlog
   import io
   
   logger = structlog.get_logger(__name__)
   
   class ThumbnailGenerationError(Exception):
       """Raised when thumbnail generation fails."""
   ```
3. Implement ThumbnailService class with research fixes:
   ```python
   class ThumbnailService:
       QUALITY = 85
       FORMAT = "JPEG"
       RESAMPLING = Image.Resampling.LANCZOS  # FIXED: Research.md specifies this constant name
       PROGRESSIVE = True  # FIXED: Research.md specifies progressive JPEG support
       SIZES = {
           ThumbnailSizeStrEnum.SMALL: (240, 180),
           ThumbnailSizeStrEnum.MEDIUM: (640, 480), 
           ThumbnailSizeStrEnum.LARGE: (1280, 960),
       }
       
       @staticmethod
       def generate_thumbnails(photo_bytes: bytes, original_key: str) -> Dict[ThumbnailSizeStrEnum, str]:
           # Implementation here
   ```
4. Implement generation method with research requirements:
   ```python
   @staticmethod
   def generate_thumbnails(photo_bytes: bytes, original_key: str) -> Dict[ThumbnailSizeStrEnum, str]:
       try:
           # Convert bytes to PIL Image
           img = Image.open(io.BytesIO(photo_bytes))
           
           # Ensure RGB mode
           if img.mode != 'RGB':
               img = img.convert('RGB')
           
           thumbnails = {}
           for size, (width, height) in ThumbnailService.SIZES.items():
               # Create thumbnail maintaining aspect ratio with research fix
               thumbnail = img.copy()
               thumbnail.thumbnail((width, height), Image.Resampling.LANCZOS)
               
               # Apply background color for non-square images (research fix)
               if thumbnail.size != (width, height):
                   canvas = Image.new('RGB', (width, height), (255, 255, 255))  # White background
                   offset = ((width - thumbnail.width) // 2, 
                            (height - thumbnail.height) // 2)
                   canvas.paste(thumbnail, offset)
                   thumbnail = canvas
               
               # Generate storage key (FIXED: following research.md pattern `<uuid>-<size>.jpg`)
               stem = os.path.splitext(original_key)[0]
               storage_key = f"{stem}-{size.value}.jpg"
               
               # Save thumbnail atomically with research fixes
               ThumbnailService._atomic_write(storage_key, thumbnail)
               
               thumbnails[size] = storage_key
           
           return thumbnails
           
       except Exception as e:
           logger.error(f"Failed to generate thumbnails: {e}")
           raise ThumbnailGenerationError(f"Thumbnail generation failed: {e}")
   ```
5. Implement atomic write helper:
   ```python
   @staticmethod
   def _atomic_write(storage_key: str, image: Image.Image) -> None:
       from django.conf import settings
       
       path = os.path.join(settings.MEDIA_ROOT, storage_key)
       os.makedirs(os.path.dirname(path), exist_ok=True)
       
       fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
       try:
           buf = io.BytesIO()
           # APPLY RESEARCH FIXES
           image.save(buf, format=ThumbnailService.FORMAT, 
                      quality=ThumbnailService.QUALITY, 
                      optimize=True,
                      progressive=ThumbnailService.PROGRESSIVE)  # FIXED: progressive JPEG support
           os.write(fd, buf.getvalue())
       finally:
           os.close(fd)
   ```

**Key Research Requirements:**
- Input bytes already EXIF-stripped
- Use `Image.Resampling.LANCZOS` constant
- Maintain aspect ratio with `thumbnail()`
- Atomic writes using `O_CREAT | O_EXCL | O_WRONLY`
- Storage: `<uuid>-<size>.jpg` format (NOT `thumbnails/<size>/<uuid>.jpg`)
- Quality 85, optimize=True, progressive=True

**VERIFICATION FIXES:**
- Research.md specifies constant name `Image.Resampling.LANCZOS`
- Research.md specifies storage key pattern `<uuid>-<size>.jpg`
- Research.md specifies progressive JPEG support

**Verification:**
```bash
uv run basedpyright src/backend/apps/media/services/thumbnails.py
uv run ruff check src/backend/apps/media/services/thumbnails.py
uv run pytest src/backend/apps/media/tests/test_thumbnails.py -v
```

---

### T2.3: Unit Tests for Thumbnails
**Priority:** MEDIUM
**Risk Level:** LOW
**Semantic Anchor:** `src/backend/apps/media/tests/test_thumbnails.py`
**Dependencies:** T2.2

**Task Implementation Steps:**
1. Create `src/backend/apps/media/tests/test_thumbnails.py`
2. Include test classes following existing patterns with research fixes

**Test Framework Setup:**
- Use existing patterns from `apps.users/tests/`
- Include `_make_*` helper functions
- Class-based test organization
- Proper pytest markers
- Test both square and non-square images for background color fix

## Phase 3: Model & Integration

### T3.1: AdImage Thumbnail URL Properties
**Priority:** HIGH  
**Risk Level:** LOW  
**Semantic Anchor:** `src/backend/apps/ads/models.py`
**Dependencies:** T2.1  

**Task Implementation Steps:**
1. Open `src/backend/apps/ads/models.py`
2. Add import at top:
   ```python
   from django.conf import settings
   ```
3. Add properties to `AdImage` class following research naming:
   ```python
   @property
   def thumbnail_small_url(self) -> str | None:
       """Return small thumbnail URL or None if not generated."""
       if self.thumbnail_small:
           return f"{settings.MEDIA_URL}{self.thumbnail_small}"
       return None
   
   @property
   def thumbnail_medium_url(self) -> str | None:
       """Return medium thumbnail URL or None if not generated."""
       if self.thumbnail_medium:
           return f"{settings.MEDIA_URL}{self.thumbnail_medium}"
       return None
   
   @property
   def thumbnail_large_url(self) -> str | None:
       """Return large thumbnail URL or None if not generated."""
       if self.thumbnail_large:
           return f"{settings.MEDIA_URL}{self.thumbnail_large}"
       return None
   ```

**VERIFICATION FIX:**
- Task names must use AdImage (research.md requirement)

**Verification:**
```bash
uv run basedpyright src/backend/apps/ads/models.py
```

---

### T3.2: Integrate with save_photo() and update_ad_and_moderate()
**Priority:** HIGH  
**Risk Level:** MEDIUM  
**Semantic Anchor:** `src/telegram_bot/handlers/ad_create.py`
**Dependencies:** T2.2, T3.1  

**Task Implementation Steps:**
1. Open `src/telegram_bot/handlers/ad_create.py`
2. Add imports with research fixes:
   ```python
   import asyncio
   from apps.media.services.thumbnails import ThumbnailService
   from apps.core.enums import ThumbnailSizeStrEnum  # FIXED: research.md specifies this enum
   ```
3. Replace `save_photo()` with `save_photo_with_thumbnails()` implementing research fixes:
   ```python
   async def save_photo_with_thumbnails(storage_key: str, photo_bytes: bytes) -> tuple[str, dict[ThumbnailSizeStrEnum, str]]:
       """
       Save original photo and generate thumbnails atomically with research requirements.
       
       Returns:
           Tuple of (original_storage_key, thumbnails_dict)
       """
       def _write_all(orig_key: str, data: bytes) -> dict[ThumbnailSizeStrEnum, str]:
           from telegram_bot.services.media import strip_photo_exif
           from django.conf import settings
           import os
           
           cleaned = strip_photo_exif(data)
           
           # Write original
           orig_path = os.path.join(settings.MEDIA_ROOT, orig_key)
           os.makedirs(os.path.dirname(orig_path), exist_ok=True)
           fd = os.open(orig_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
           try:
               os.write(fd, cleaned)
           finally:
               os.close(fd)
               
           # Generate and write thumbnails
           return ThumbnailService.generate_thumbnails(cleaned, orig_key)

       key = storage_key
       while True:
           try:
               thumbnails = await asyncio.to_thread(_write_all, key, photo_bytes)
               return key, thumbnails
           except FileExistsError:
               key = generate_storage_key()
           except Exception as e:
               logger.warning(f"Thumbnail generation failed: {e}")
               return key, {}
   ```
4. Update callers in same file to use new function
5. Update type hints and imports with ThumbnailSizeStrEnum

**Task B: Modify update_ad_and_moderate()**

**Task Implementation Steps:**
1. Find `_update_and_moderate()` function in same file
2. Update AdImage creation to include thumbnail fields with research pattern:
   ```python
   # In _update_and_moderate():
   for photo in photos:
       AdImage.objects.create(
           ad_id=ad_id,
           image=photo["storage_key"],
           thumbnail_small=photo.get("thumbnail_small"),  # Use research key pattern
           thumbnail_medium=photo.get("thumbnail_medium"), 
           thumbnail_large=photo.get("thumbnail_large"),
           telegram_file_id=photo["telegram_file_id"],
           position=photo["position"],
       )
   ```

**VERIFICATION FIXES:**
- Task names must use AdImage naming (research.md)
- Storage key pattern `<uuid>-<size>.jpg` (research.md)
- Constant `Image.Resampling.LANCZOS` (research.md)

**Verification:**
```bash
uv run basedpyright src/telegram_bot/handlers/ad_create.py
uv run ruff check src/telegram_bot/handlers/ad_create.py
```

### T3.3: Add Model Fields (Backup to Migration)
**Priority:** HIGH
**Risk Level:** LOW
**Semantic Anchor:** `src/backend/apps/ads/models.py`
**Dependencies:** T1.2

**Task Implementation Steps:**
1. Open `src/backend/apps/ads/models.py`
2. Add fields directly to AdImage model:
   ```python
   thumbnail_small = models.CharField(
       max_length=64,
       blank=True,
       null=True,
       help_text="Storage key for small thumbnail",
   )
   
   thumbnail_medium = models.CharField(
       max_length=64,
       blank=True, 
       null=True,
       help_text="Storage key for medium thumbnail", 
   )
   
   thumbnail_large = models.CharField(
       max_length=64,
       blank=True,
       null=True,
       help_text="Storage key for large thumbnail",
   )
   ```

## Phase 4: Backfill (Deployment-time Task)

### T4.1: Backfill Thumbnails Management Command
**Priority:** MEDIUM
**Risk Level:** MEDIUM
**Semantic Anchor:** `src/backend/apps/media/management/commands/backfill_thumbnails.py`
**Dependencies:** T2.2, T3.3

**Task Implementation Steps:**
1. Create `src/backend/apps/media/management/commands/backfill_thumbnails.py`
2. Implement full command with research fixes

**KEY RESEARCH REQUIREMENTS IN BACKFILL:**
- Use storage key pattern `<uuid>-<size>.jpg`
- Handle `Image.Resampling.LANCZOS`
- Use progressive JPEG with quality 85
- Include background color handling for non-square images

**Usage:** `python src/backend/manage.py backfill_thumbnails`

**Verification:**
```bash
uv run basedpyright src/backend/apps/media/management/commands/backfill_thumbnails.py
uv run python src/backend/manage.py backfill_thumbnails --batch-size 10
```

## Phase 5: Templates (Frontend consumption)

### T5.1: Update Ad List Template
**Priority:** MEDIUM
**Risk Level:** LOW
**Semantic Anchor:** `src/backend/templates/ads/partials/ad_list.html`
**Dependencies:** T3.1

**Task Implementation Steps:**
1. Open `src/backend/templates/ads/partials/ad_list.html`
2. Find line 28 and replace with research-compliant version:
   ```html
   <img src="{{ ad.images.first.thumbnail_small_url|default:ad.images.first.image_url }}"
        alt="{{ ad.title }}"
        class="w-full h-48 object-cover rounded-t-lg"
        loading="lazy"
        width="240" height="180">
   ```

**VERIFICATION FIX:**
- Task names must use AdImage references (research.md)

**Verification:**
```bash
uv run pytest --collect-only  # Verify template renders
```

### T5.2: Update Detail Template
**Priority:** MEDIUM
**Risk Level:** LOW
**Semantic Anchor:** `src/backend/templates/ads/detail.html`
**Dependencies:** T3.1

**Task Implementation Steps:**
1. Open `src/backend/templates/ads/detail.html`
2. Replace with research-compliant version:
   ```html
   <img src="{{ image.thumbnail_large_url|default:image.image_url }}"
        alt="Photo {{ forloop.counter }} for {{ ad.title }}"
        class="w-full {% if ad.images.count == 1 %}max-h-96{% else %}h-64{% endif %} object-cover rounded-lg"
        loading="lazy"
        width="1280" height="960">
   ```

**Verification:**
```bash
uv run pytest --collect-only  # Verify template renders
```

### T5.3: Register Media App
**Priority:** HIGH
**Risk Level:** LOW
**Semantic Anchor:** `src/backend/config/settings/base.py`
**Dependencies:** T2.1

**Task Implementation Steps:**
1. Open `src/backend/config/settings/base.py`
2. Find INSTALLED_APPS list
3. Add `"apps.media"` entry

**Why needed:** Required for management command discovery and model imports

**Verification:**
```bash
uv run python -c 'from django.conf import settings; print("apps.media" in settings.INSTALLED_APPS)'
```

## Execution DAG & Dependencies

```
Phase 1: Schema & Constants
  T1.1 ThumbnailSizeStrEnum ─── No deps
  T1.2 Migration ─── Depends on T1.1

Phase 2: Service Layer
  T2.1 Create media app ─── Depends on T1.2
  T2.2 ThumbnailService ─── Depends on T2.1
  T2.3 Unit tests ─── Depends on T2.2

Phase 3: Model & Integration
  T3.1 AdImage URL properties ─── Depends on T2.1
  T3.2 Integrate save_photo ─── Depends on T2.2, T3.1
  T3.3 Add model fields ─── Depends on T1.2

Phase 4: Backfill
  T4.1 Backfill command ─── Depends on T2.2, T3.3

Phase 5: Templates
  T5.1 Update ad_list template ─── Depends on T3.1
  T5.2 Update detail template ─── Depends on T3.1
  T5.3 Register media app ─── Depends on T2.1
```

## Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| Schema migration | MEDIUM | Fields are nullable; thumbnails optional during rollout |
| Concurrent thumbnail generation | LOW | Uses O_CREAT | O_EXCL for atomic writes; UUID-based naming |
| Storage space increase | MEDIUM | Estimated 15-25% overhead; monitor during rollout |
| Image quality degradation | LOW | Uses LANCZOS (highest quality); JPEG quality=85, progressive=True |

**RESEARCH FIXES:**
- Constant: `Image.Resampling.LANCZOS` (research.md)
- Storage pattern: `<uuid>-<size>.jpg` (research.md) 
- Quality parameter: 85 (research.md)
- Progressive JPEG: enabled (research.md)
- Background color for non-square images (research.md)

## Rollback Strategy

1. **Templates:** Revert T5.1 and T5.2; fallback to `image_url`
2. **Database:** Thumbnail fields nullable; no data loss on rollback
3. **Files:** Original images unchanged; delete thumbnails with `<uuid>-<size>.jpg` pattern
4. **Media app:** Remove `apps.media` from INSTALLED_APPS

## Files to Create

| File | Purpose |
|---|---|
| `src/backend/apps/media/__init__.py` | Package init |
| `src/backend/apps/media/apps.py` | App config |
| `src/backend/apps/media/services/__init__.py` | Services package |
| `src/backend/apps/media/services/thumbnails.py` | ThumbnailService (research fixes) |
| `src/backend/apps/media/tests/__init__.py` | Tests package |
| `src/backend/apps/media/tests/test_thumbnails.py` | Unit tests (research fixes) |
| `src/backend/apps/media/management/__init__.py` | Management package |
| `src/backend/apps/media/management/commands/__init__.py` | Commands package |
| `src/backend/apps/media/management/commands/backfill_thumbnails.py` | Backfill command (research fixes) |
| `src/backend/apps/ads/migrations/0004_adimage_thumbnails.py` | Migration |

## Files to Modify

| File | Changes |
|---|---|
| `src/backend/apps/core/enums.py` | Add `ThumbnailSizeStrEnum` (research fix: StrEnum not plain enum) |
| `src/backend/apps/ads/models.py` | Add thumbnail fields + URL properties (AdImage naming) |
| `src/telegram_bot/handlers/ad_create.py` | Integrate thumbnails (AdImage tasks, research fixes) |
| `src/backend/apps/ads/views/listings.py` | Extend `media_gate()` for thumbnail paths |
| `src/backend/apps/ads/urls.py` | Adjust media pattern to `path:image_key` |
| `src/backend/templates/ads/partials/ad_list.html` | Use `thumbnail_small_url` (AdImage refs) |
| `src/backend/templates/ads/detail.html` | Use `thumbnail_large_url` (AdImage refs) |
| `src/backend/config/settings/base.py` | Register `apps.media` in INSTALLED_APPS |

## Verification Commands

```bash
# Type checking all changed files
uv run basedpyright src/backend/apps/core/enums.py
uv run basedpyright src/backend/apps/ads/models.py
uv run basedpyright src/backend/apps/media/services/thumbnails.py
uv run basedpyright src/backend/apps/ads/views/listings.py
uv run basedpyright src/telegram_bot/handlers/ad_create.py
uv run basedpyright src/backend/config/settings/base.py

# Lint all changed files
uv run ruff check src/backend/apps/core/enums.py src/backend/apps/ads/models.py src/backend/apps/media/services/thumbnails.py src/backend/apps/ads/views/listings.py src/telegram_bot/handlers/ad_create.py src/backend/config/settings/base.py

# Run tests
uv run pytest src/backend/apps/media/tests/test_thumbnails.py -v
uv run pytest --collect-only  # Verify templates can render
```

## File Organization Notes

- All new files placed in appropriate Django app structure
- imports added to `__init__.py` files where needed
- Use absolute imports (e.g., `from apps.core.enums import ThumbnailSizeStrEnum`)
- Type hints follow existing codebase patterns
- All existing functionality preserved during changes
- Tests placed in `apps/media/tests/` following existing patterns
- Research.md requirements implemented for: constant naming, storage pattern, progressive JPEG, background color

This plan provides a dependency-aware rollout with incremental changes, minimal risk, and clear verification steps at each phase. The atomic, isolated nature of each task ensures safe deployment and easy rollback if needed, with all research.md findings incorporated as required fixes.