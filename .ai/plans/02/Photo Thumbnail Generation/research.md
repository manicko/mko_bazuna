# Research Report: Photo Thumbnail Generation

> **Date:** 2026-07-26
> **Context:** Phase 2 Plan 1 — Photo Thumbnail Generation
> **Source Plans:** `.ai/plans/photo-thumbnail-generation-plan.yaml`, `.ai/plans/phase-02-detailed-plan-1.md` (§2)

---

## 1. Current State Analysis

### 1.1 Existing Photo Pipeline (Fully Functional)

The codebase already has a working photo pipeline for Telegram bot → filesystem:

| Component | File | Status |
|---|---|---|
| **JPEG validation** | `src/telegram_bot/services/media.py:29` — `validate_photo()` | ✅ Implemented |
| **EXIF stripping** | `src/telegram_bot/services/media.py:98` — `strip_photo_exif()` | ✅ Implemented |
| **UUID key generation** | `src/telegram_bot/services/media.py:75` — `generate_storage_key()` | ✅ Implemented |
| **Atomic file write** | `src/telegram_bot/handlers/ad_create.py:442` — `save_photo()` | ✅ Implemented |
| **Photo deletion** | `src/telegram_bot/services/media.py:80` — `delete_photo()` | ✅ Implemented |
| **AdImage model** | `src/backend/apps/ads/models.py:316` | ✅ Implemented |
| **Media gate (X-Accel-Redirect)** | `src/backend/apps/ads/views/listings.py:54` — `media_gate()` | ✅ Implemented |
| **Pillow dependency** | `pyproject.toml:20` — `pillow>=10.4.0` | ✅ Present |

### 1.2 Current Photo Storage Layout

```
MEDIA_ROOT/                    # e.g., /app/media
└── <uuid>.jpg                 # Flat directory, all originals
```

### 1.3 Current Template Usage

| Template | Line | Current Code | Issue |
|---|---|---|---|
| `templates/ads/partials/ad_list.html` | 28 | `{{ ad.images.first.image_url }}` | Full-size image in 240px grid card |
| `templates/ads/detail.html` | 32 | `{{ image.image_url }}` | Full-size image in gallery |

### 1.4 Current Media Gate Flow

```
Client → /media/<uuid>.jpg → media_gate() → checks AdImage.ad.status == PUBLISHED
→ X-Accel-Redirect: /protected-media/<uuid>.jpg → nginx serves file
```

The gate looks up `AdImage` by `image` field (the original storage key). It does **not** currently support serving thumbnails.

### 1.5 Existing EXIF Handling

`strip_photo_exif()` in `telegram_bot/services/media.py:98` already uses:
- `ImageOps.exif_transpose(img)` — corrects orientation
- `img.info.pop("exif", None)` — strips metadata
- `img.save(buf, format="JPEG", optimize=True)` — re-encodes

This function runs **at upload time** in `save_photo()`, so the stored original is already EXIF-free and orientation-corrected. **Thumbnails generated from this clean data do NOT need their own EXIF handling.**

---

## 2. Gap Analysis

| # | What's Missing | Source Plan Ref | Risk | Rationale |
|---|---|---|---|---|
| G1 | `ThumbnailSize` StrEnum | T1.1 | Low | Simple enum, no DB impact |
| G2 | Thumbnail fields on `AdImage` model | T1.2, T3.3 | Medium | Migration required; nullable fields safe |
| G3 | `apps/media` app structure | T2.1 | Low | New Django app registration |
| G4 | `ThumbnailService` class | T2.2 | Low | Pillow thumbnail + atomic write |
| G5 | Integration with `save_photo()` | T3.2 | Medium | Bot handler changes |
| G6 | Integration with `update_ad_and_moderate()` | T3.2 | Medium | AdImage creation changes |
| G7 | Thumbnail URL properties on `AdImage` | T3.1 | Low | Property methods only |
| G8 | Backfill management command | T4.1 | Medium | Iterates all existing AdImage records |
| G9 | Template updates (list + detail) | T5.1, T5.2 | Low | Template variable changes |
| G10 | Media gate for thumbnails | — | Low | Need to handle thumbnail storage keys |
| G11 | Cache-Control headers for thumbnails | §2.2 | Low | Middleware or nginx config |
| G12 | `media` app registration in INSTALLED_APPS | T5.3 | Low | Single line in settings |

### 2.1 Design Decisions from Plan (Not Yet Coded)

- **Storage layout:** `MEDIA_ROOT/thumbnails/{small,medium,large}/<uuid>.jpg`
- **File naming:** Original `<uuid>.jpg` → thumbnails use same `<uuid>.jpg` in subdirectories
- **Variants:** Small (240×180), Medium (640×480), Large (1280×960)
- **Quality:** JPEG quality=85, optimize=True
- **Resampling:** `Image.LANCZOS` (highest quality)
- **Atomic writes:** Reuse `O_CREAT | O_EXCL` pattern from existing `save_photo()`

---

## 3. Implementation Recommendations

### 3.1 Thumbnail Storage Key Strategy

**Recommendation:** Use a derived key path rather than separate DB fields per size.

The plan proposes separate `thumbnail_small`, `thumbnail_medium`, `thumbnail_large` CharFields on `AdImage`. This is correct for the relational model, but the **storage key naming** should follow a convention that allows derivation from the original key:

```python
# Original: <uuid>.jpg
# Thumbnail variants: thumbnails/<variant>/<uuid>.jpg

def thumbnail_storage_key(original_key: str, size: ThumbnailSize) -> str:
    stem = original_key  # e.g., "a1b2c3d4.jpg"
    return f"thumbnails/{size.value}/{stem}"
```

This makes the `media_gate` view extensible: if the `image_key` starts with `thumbnails/`, serve from the corresponding subdirectory.

### 3.2 ThumbnailService API

```python
class ThumbnailService:
    """Generates thumbnail variants for uploaded images."""

    QUALITY = 85
    FORMAT = "JPEG"
    RESAMPLING = Image.LANCZOS

    @staticmethod
    def generate_thumbnails(photo_bytes: bytes, original_key: str) -> dict[ThumbnailSize, str]:
        """
        Generate three thumbnail variants from clean (EXIF-stripped) JPEG bytes.

        Args:
            photo_bytes: EXIF-free JPEG bytes (already processed by strip_photo_exif)
            original_key: Original storage key (e.g., "<uuid>.jpg")

        Returns:
            Dict mapping ThumbnailSize -> storage key for each variant.

        Raises:
            ThumbnailGenerationError: If image processing fails.
        """
```

Key implementation details:
- **No re-EXIF handling needed** — photo_bytes are already cleaned by `strip_photo_exif()` at upload time
- **`Image.thumbnail()`** maintains aspect ratio (does not crop/stretch)
- **Background color** for non-square images: white (255,255,255) fill if needed
- **Atomic write** per file: `os.open(path, O_CREAT | O_EXCL | O_WRONLY)`

### 3.3 Media Gate Extension

The existing `media_gate()` (`listings.py:54`) looks up `AdImage` by `image=image_key`. For thumbnails:

```python
def media_gate(request: HttpRequest, image_key: str) -> HttpResponse:
    # If requesting a thumbnail, extract the original key from the path
    is_thumbnail, original_key = parse_thumbnail_key(image_key)
    lookup_key = original_key if is_thumbnail else image_key

    try:
        ad_image = AdImage.objects.select_related("ad").get(image=lookup_key)
    except AdImage.DoesNotExist:
        raise Http404("Image not found")

    # Staff bypass
    if request.user.is_staff:
        response = HttpResponse()
        response["X-Accel-Redirect"] = f"/protected-media/{image_key}"
        return response

    # Non-staff: only PUBLISHED ads
    if ad_image.ad.status != AdStatus.PUBLISHED:
        return HttpResponseForbidden("Access denied")

    response = HttpResponse()
    response["X-Accel-Redirect"] = f"/protected-media/{image_key}"
    return response
```

**Alternative (simpler):** Keep `media_gate` unchanged. Add a separate URL pattern `/media/thumbnails/<variant>/<uuid>.jpg` that serves thumbnails directly without DB lookup (since thumbnail access implies the original is authorized). The plan's YAML doesn't specify this but it reduces DB queries on listing pages.

**Recommended approach:** Extend the single gateway with thumbnail path parsing. The existing pattern `media/<str:image_key>` already matches paths with slashes when using `path()` instead of `re_path()`. The URL pattern may need adjustment:

```python
# In urls.py:
path("media/<path:image_key>", media_gate, name="media_gate"),
```

### 3.4 Integration in `save_photo()` (Bot Handler)

Current flow in `src/telegram_bot/handlers/ad_create.py:442`:

```python
async def save_photo(storage_key: str, photo_bytes: bytes) -> str:
    def _write(path, data):
        cleaned = strip_photo_exif(data)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, O_CREAT | O_EXCL | O_WRONLY)
        try:
            os.write(fd, cleaned)
        finally:
            os.close(fd)
    # ... atomic write loop
```

**Recommendation:** Create a new async helper `save_photo_with_thumbnails()`:

```python
async def save_photo_with_thumbnails(storage_key: str, photo_bytes: bytes) -> tuple[str, dict[ThumbnailSize, str]]:
    """
    Save original photo and generate thumbnails.

    Returns:
        Tuple of (original_storage_key, thumbnails_dict).
    """
    def _write_all(orig_key: str, data: bytes) -> dict[ThumbnailSize, str]:
        cleaned = strip_photo_exif(data)
        # Write original
        orig_path = os.path.join(settings.MEDIA_ROOT, orig_key)
        os.makedirs(os.path.dirname(orig_path), exist_ok=True)
        fd = os.open(orig_path, O_CREAT | O_EXCL | O_WRONLY)
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
        except ThumbnailGenerationError as e:
            logger.warning(f"Thumbnail generation failed: {e}")
            # Fallback: save original only, return empty thumbnails
            return key, {}
```

### 3.5 Integration in `update_ad_and_moderate()`

Current flow creates AdImage with only `image` and `telegram_file_id`. Must add `thumbnail_small`, `thumbnail_medium`, `thumbnail_large`:

```python
# In _update_and_moderate():
for photo in photos:
    AdImage.objects.create(
        ad_id=ad_id,
        image=photo["storage_key"],
        thumbnail_small=photo.get("thumbnail_small"),
        thumbnail_medium=photo.get("thumbnail_medium"),
        thumbnail_large=photo.get("thumbnail_large"),
        telegram_file_id=photo["telegram_file_id"],
        position=photo["position"],
    )
```

### 3.6 Template Updates

**`ad_list.html` (line 28):**
```html
<img src="{{ ad.images.first.thumbnail_small_url|default:ad.images.first.image_url }}"
     alt="{{ ad.title }}"
     class="w-full h-48 object-cover rounded-t-lg"
     loading="lazy"
     width="240" height="180">
```

**`detail.html` (line 32):**
```html
<img src="{{ image.thumbnail_large_url|default:image.image_url }}"
     alt="Photo {{ forloop.counter }} for {{ ad.title }}"
     class="w-full {% if ad.images.count == 1 %}max-h-96{% else %}h-64{% endif %} object-cover rounded-lg"
     loading="lazy"
     width="1280" height="960">
```

### 3.7 AdImage Model URL Properties

```python
@property
def thumbnail_small_url(self) -> str | None:
    from django.conf import settings
    if self.thumbnail_small:
        return f"{settings.MEDIA_URL}{self.thumbnail_small}"
    return None

@property
def thumbnail_medium_url(self) -> str | None:
    from django.conf import settings
    if self.thumbnail_medium:
        return f"{settings.MEDIA_URL}{self.thumbnail_medium}"
    return None

@property
def thumbnail_large_url(self) -> str | None:
    from django.conf import settings
    if self.thumbnail_large:
        return f"{settings.MEDIA_URL}{self.thumbnail_large}"
    return None
```

---

## 4. Pillow Best Practices for Thumbnail Generation

### 4.1 EXIF Handling

The existing `strip_photo_exif()` already runs `ImageOps.exif_transpose()` before storage. The saved original JPEG has:
- No EXIF orientation tag
- Correct pixel orientation
- Standard sRGB color space

**Thumbnail generation does NOT need repeated EXIF handling** because the input bytes are already clean.

### 4.2 Resampling Quality

| Filter | Quality | Performance | Use Case |
|---|---|---|---|
| `Image.LANCZOS` | Highest | Slowest | Downscaling (thumbnails) |
| `Image.BICUBIC` | High | Medium | General resize |
| `Image.BILINEAR` | Medium | Fast | Real-time |
| `Image.NEAREST` | Low | Fastest | Pixel art |

**Recommendation:** Use `Image.LANCZOS` for all thumbnail generation. The downscaling is done once at upload time, so performance is not critical.

### 4.3 Aspect Ratio Preservation

```python
def _generate_variant(img: Image.Image, max_size: tuple[int, int]) -> Image.Image:
    """Generate thumbnail maintaining aspect ratio with white background."""
    img = img.copy()
    img.thumbnail(max_size, Image.LANCZOS)

    # If the thumbnail doesn't fill the max dimensions, create a canvas
    if img.size != max_size:
        canvas = Image.new("RGB", max_size, (255, 255, 255))
        offset = (
            (max_size[0] - img.width) // 2,
            (max_size[1] - img.height) // 2,
        )
        canvas.paste(img, offset)
        return canvas

    return img
```

**Note:** The plan's YAML specifies "maintain aspect ratio via thumbnail() method" but templates use `object-fit: cover` CSS. The combination means thumbnails don't need explicit canvas padding — Pillow's `thumbnail()` preserves aspect ratio inside the box, and CSS `object-fit: cover` crops to fill on the client. Either approach works; the simpler one is `thumbnail()` without canvas padding.

### 4.4 JPEG Quality Settings

```python
img.save(buf, format="JPEG", quality=85, optimize=True)
```

- `quality=85`: Sweet spot for visual quality vs file size
- `optimize=True`: Huffman optimization (slightly slower save, ~5-10% smaller files)
- `progressive=False` (default): Baseline JPEG (faster to decode, preferred for thumbnails)

### 4.5 Atomic File Write Pattern (Existing + Extended)

The existing `save_photo()` already demonstrates the correct pattern:

```python
os.makedirs(os.path.dirname(path), exist_ok=True)
fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
try:
    os.write(fd, data)
finally:
    os.close(fd)
```

This guarantees:
- **No partial writes** visible to readers (file either fully written or doesn't exist)
- **No race conditions** between concurrent uploads (collision = `FileExistsError` → retry)
- **No temporary file cleanup** needed

---

## 5. Storage Layout Recommendations

```
MEDIA_ROOT/
├── <uuid>.jpg                          # Original (existing)
└── thumbnails/
    ├── small/
    │   └── <uuid>.jpg                  # 240×180
    ├── medium/
    │   └── <uuid>.jpg                  # 640×480
    └── large/
        └── <uuid>.jpg                  # 1280×960
```

This layout:
- Keeps originals and thumbnails separate (clean rollback: delete `thumbnails/`)
- Uses same UUID stem for easy derivation
- Works with `X-Accel-Redirect` to `/protected-media/thumbnails/small/<uuid>.jpg`
- Allows nginx to serve thumbnails with `Cache-Control: public, max-age=31536000, immutable`

---

## 6. Dependencies on Other Modules

| Module | Dependency Type | Details |
|---|---|---|
| `apps.ads.models.AdImage` | Data model | Thumbnail fields added here |
| `apps.ads.views.listings.media_gate` | Serving | Must handle thumbnail paths |
| `telegram_bot.services.media` | Photo pipeline | `strip_photo_exif()` provides clean input |
| `telegram_bot.handlers.ad_create` | Integration | `save_photo()` and `update_ad_and_moderate()` modified |
| `apps.core.enums` | Constants | `ThumbnailSize` enum added |
| `apps.ads.urls` | Routing | May need path pattern adjustment |
| `templates/ads/partials/ad_list.html` | Frontend | Use `thumbnail_small_url` |
| `templates/ads/detail.html` | Frontend | Use `thumbnail_large_url` or `thumbnail_medium_url` |
| `apps.ads.migrations` | Schema | New migration for thumbnail fields |
| `apps.core.config.INSTALLED_APPS` | Registration | Must add `apps.media` |

### 6.1 No Dependencies On

- **Redis/caching** — thumbnails are static files, no cache layer needed for generation
- **Celery/async tasks** — generation happens synchronously at upload time (fast enough)
- **S3 storage** — filesystem storage assumed; abstraction via `STORAGES` config for future S3 swap
- **User authentication** — `media_gate` already handles access control

---

## 7. Implementation Order (Execution DAG)

```
Phase 1: Schema & Constants
  T1.1 ThumbnailSize enum          ─── No deps
  T1.2 Migration                    ─── Depends on T1.1

Phase 2: Service Layer
  T2.1 Create media app             ─── Depends on T1.2
  T2.2 ThumbnailService             ─── Depends on T2.1
  T2.3 Unit tests                   ─── Depends on T2.2

Phase 3: Model & Integration
  T3.1 AdImage URL properties       ─── Depends on T2.1
  T3.2 Integrate save_photo         ─── Depends on T2.2, T3.1
  T3.3 Add model fields             ─── Depends on T1.2

Phase 4: Backfill
  T4.1 Backfill command             ─── Depends on T2.2, T3.3

Phase 5: Templates
  T5.1 Update ad_list template      ─── Depends on T3.1
  T5.2 Update detail template       ─── Depends on T3.1
  T5.3 Register media app           ─── Depends on T2.1
```

---

## 8. Rollback Strategy

The plan's YAML specifies a clean rollback path:

1. **Templates** — revert T5.1 and T5.2 changes; templates fall back to `image_url`
2. **Database** — thumbnail fields are `null=True`; no data loss on rollback
3. **Files** — original images are never modified; delete `thumbnails/` directory
4. **Media app** — remove `apps.media` from INSTALLED_APPS

---

## 9. Files to Create

| File | Purpose |
|---|---|
| `src/backend/apps/media/__init__.py` | Package init |
| `src/backend/apps/media/apps.py` | App config |
| `src/backend/apps/media/services/__init__.py` | Services package |
| `src/backend/apps/media/services/thumbnails.py` | ThumbnailService |
| `src/backend/apps/media/tests/__init__.py` | Tests package |
| `src/backend/apps/media/tests/test_thumbnails.py` | Thumbnail tests |
| `src/backend/apps/media/management/__init__.py` | Management package |
| `src/backend/apps/media/management/commands/__init__.py` | Commands package |
| `src/backend/apps/media/management/commands/backfill_thumbnails.py` | Backfill command |
| `src/backend/apps/ads/migrations/0004_adimage_thumbnails.py` | Migration |

## 10. Files to Modify

| File | Changes |
|---|---|
| `src/backend/apps/core/enums.py` | Add `ThumbnailSize` StrEnum |
| `src/backend/apps/ads/models.py` | Add thumbnail fields + URL properties |
| `src/telegram_bot/handlers/ad_create.py` | Integrate thumbnails in `save_photo()` and `update_ad_and_moderate()` |
| `src/backend/apps/ads/views/listings.py` | Extend `media_gate()` for thumbnail paths |
| `src/backend/apps/ads/urls.py` | Adjust media pattern to `path:image_key` |
| `src/backend/templates/ads/partials/ad_list.html` | Use thumbnail_small_url |
| `src/backend/templates/ads/detail.html` | Use thumbnail_large_url |
| `src/backend/config/settings/base.py` | Register `apps.media` in INSTALLED_APPS |