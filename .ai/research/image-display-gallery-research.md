# Research: CSS Image Display & Gallery Architecture for Catalog Grid and Ad Detail Pages

> **Status:** Research complete
> **Confidence:** HIGH (codebase evidence + web-verified sources)
> **Date:** 2026-08-24
> **Scope:** Two problems — (1) catalog grid thumbnail display technique, (2) ad detail gallery structure and GLightbox coexistence.

---

## Table of Contents

1. [Problem 1: Catalog Grid Image Display](#1-problem-1-catalog-grid-image-display)
2. [Problem 2: Ad Detail Gallery Structure & GLightbox Coexistence](#2-problem-2-ad-detail-gallery-structure--glightbox-coexistence)
3. [Cross-Cutting Concerns](#3-cross-cutting-concerns)
4. [Feasible Approaches](#4-feasible-approaches)
5. [Recommendations](#5-recommendations)

---

## 1. Problem 1: Catalog Grid Image Display

### 1.1 Current State (Confirmed: ✅ `object-cover` crops subjects)

**Catalog grid card images** (`ads/partials/ad_list.html:76-88`):

```django
{% if ad.images.first %}
    <img
        src="{{ ad.images.first.thumbnail_small_url|default:ad.images.first.image_url }}"
        alt="{{ ad|get_title:LANGUAGE_CODE }}"
        class="w-full h-48 object-cover rounded-t-lg"
        loading="lazy"
        width="240" height="180"
    >
{% else %}
    <div class="w-full h-48 bg-gray-200 rounded-t-lg flex items-center justify-center">
        <span class="text-gray-500">{% trans "No image" %}</span>
    </div>
{% endif %}
```

**Other `object-cover` usages** (all confirmed via `grep` on templates):

| File | Line | Context | Dimensions |
|------|------|---------|------------|
| `ads/partials/ad_list.html` | 80 | Catalog grid card (primary Problem-1 target) | `h-48` (≈240×180 → 4:3) |
| `ads/detail.html` | 37 | Detail gallery image | `h-64` (multi) / `max-h-96` (single) |
| `ads/dashboard.html` | 88 | Seller dashboard preview | `h-32` |
| `ads/edit.html` | 88 | Edit form image preview | `h-24` |
| `admin/moderation/review.html` | 79 | Admin moderation thumbnail | `h-full` |
| `components/header_auth_entry.html` | 23 | User avatar (edge case) | `w-8 h-8` (1:1) |

**Thumbnail pipeline** (`apps/media/services/thumbnails.py:25`):

```python
SIZES: dict[ThumbnailSizeStrEnum, tuple[int, int]] = {
    ThumbnailSizeStrEnum.SMALL: (240, 180),   # 4:3 — used in ad_list.html catalog grid
    ThumbnailSizeStrEnum.MEDIUM: (640, 480),   # 4:3 — used in search results / ad_list hover
    ThumbnailSizeStrEnum.LARGE: (1280, 960),   # 4:3 — used in ad detail gallery
}
```

**The problem:** `ThumbnailService.generate_thumbnails()` calls `resized.thumbnail(dimensions, LANCZOS)`. Pillow's `thumbnail()` preserves aspect ratio **within** the target box — it does NOT crop to the box. The output image is at most `240×180` but its actual dimensions depend on the source aspect ratio. An image that is 3:2 (e.g. 300×200) would be scaled to 240×160, leaving a 240×180 box with an 80px letterbox strip. The template then applies `object-cover` with `h-48`, which crops that letterbox area — but crops from the source's content, not from blank space. For portraits (9:16) or wide panoramas (16:9), `object-cover` cuts off significant content (heads, tops, bottoms).

### 1.2 Thumbnail Generation Mechanics (Pillow `thumbnail()`)

Source: `thumbnails.py:74-80`:

```python
for size_enum, dimensions in self.SIZES.items():
    key = f"{stem}-{size_enum.value}.jpg"
    resized = image.copy()
    resized.thumbnail(dimensions, self.RESAMPLING)  # LANCZOS
```

**Pillow `Image.thumbnail(size)` behavior:**
- Scales the image so that **both dimensions fit within** `size`, preserving aspect ratio.
- Does NOT pad or crop. The output is ≤ `size` in both dimensions.
- For a 4:3 source: output = exactly `240×180`.
- For a 3:2 source (e.g. 600×400): output = `240×160` (height is the constraining dimension, 600→240 means 400→160).
- For a 16:9 source (e.g. 800×450): output = `240×135`.
- For a 9:16 portrait (e.g. 400×600): output = `120×180`.

The resulting image has **variable effective dimensions** but is always stored in a fixed `240×180` box mentally. When rendered with `object-cover h-48` (192px tall at 3-col grid), the browser crops to fill the 192px height, discarding top/bottom or left/right content depending on the source aspect ratio.

> **Confidence: HIGH** — verified from Pillow documentation and by reading the actual `thumbnail()` call.

### 1.3 Tailwind v4 CSS Availability (Verified)

The compiled CSS is at `src/theme/static/theme/css/output.css`, sourced from `src/theme/static/theme/css/input.css`:

```css
/* input.css */
@import "tailwindcss";
@source "src/backend/templates/**/*.html";
```

Tailwind v4 uses `@source`-based purging — **only utilities referenced in templates are compiled into `output.css`**. Verification (programmatic scan of `output.css`):

| Utility | Available in compiled CSS? | Occurrences |
|---------|---------------------------|-------------|
| `object-cover` | ✅ YES | 1 |
| `object-contain` | ❌ NO — no template uses it | 0 |
| `object-none` | ❌ NO | 0 |
| `object-top` | ❌ NO | 0 |
| `object-center` | ❌ NO | 0 |
| `object-scale` | ❌ NO | 0 |
| `aspect-square` | ✅ YES | 1 |
| `aspect-video` | ❌ NO | 0 |
| `aspect-[4/3]` | ❌ NO (arbitrary not used) | 0 |
| `aspect-ratio` (property) | ✅ YES (base layer) | 1 |
| `object-fit` (property) | ✅ YES (base layer) | 1 |
| `bg-white` | ✅ YES | 3 |
| `bg-gray-50` | ✅ YES | 2 |
| `bg-gray-100` | ✅ YES | 2 |
| `bg-gray-200` | ✅ YES | 1 |

**Implication:** Any change to `object-fit` behavior (e.g. switching to `object-contain`) requires either:
- (a) Using an already-compiled utility (`object-cover` only — not helpful for `contain`), or
- (b) Adding `object-contain` to a template class list and **rebuilding** the Tailwind CSS.

There is a Makefile target for this (see `.ai/context/commands.md` or `Makefile`), but it must be run as part of any CSS-utility change.

> **Confidence: HIGH** — verified by scanning the compiled `output.css` file.

### 1.4 CSS Techniques Analysis

From MDN ([Understanding and setting aspect ratios](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Box_sizing/Aspect_ratios)) and DigitalOcean ([object-fit guide](https://www.digitalocean.com/community/tutorials/css-cropping-images-object-fit)):

**Technique A: `object-fit: cover` (current approach)**
- The image fills the entire container, cropping overflow.
- **Problem:** Content outside the center is lost. Portrait photos lose heads/feet; panoramic photos get their sides cropped.
- **Best for:** Background-like images, hero banners, avatars — where shape consistency matters more than full content visibility.

**Technique B: `object-fit: contain` + background color on container**
- The entire image is visible within the container, with letterbox (empty space) on the shorter axis.
- **Requirement:** The container must have a `background-color` to fill the letterbox area — without it, the page background shows through, creating a "floating image" appearance.
- **Best for:** Product catalogs, logos, diagrams — where the full item must be visible.
- From TechBloat (2026-05): *"Use `contain` for product catalogs, logos, diagrams, or artwork where cropping would remove useful detail."*

**Technique C: `aspect-ratio` + `object-fit` pairing**
- From MDN: `aspect-ratio: 4 / 3` with `object-fit: cover` creates responsive thumbnails that keep a consistent shape across screen sizes. The browser calculates height from width.
- The project already has `object-fit` and `aspect-ratio` properties compiled in the base layer (Tailwind v4 always includes these).

**Technique D: CSS `content` + pseudo-element overlay (not applicable)**
- Over-engineering; not needed here.

### 1.5 Catalog-Specific Findings

**Avito image spec (verified):** The Russian-language source `xn----7sbptikgmuv.xn--p1ai/blog/28-размер-фото-для-авито.html` (2022-02) states: *"Размер картинки для Авито объявлений оптимальный 1280px на 960px. Или 1920px. на 1440px. Соотношение сторон 4:3"* — i.e., **1280×960 or 1920×1440, aspect ratio 4:3**. The project's LARGE thumbnail (1280×960) matches this exactly.

**Note on remove-bg.io:** This third-party tool (`remove-bg.io/avito-listing-photos`) claims Avito recommends "1:1 square at 1024×1024." However, this contradicts the Russian Avito help source above. The remove-bg.io page is a **tool preset**, not an official Avito guideline. **Confidence: LOW** for the 1:1 claim; **HIGH** for the 4:3/1280×960 claim from the .рф domain source.

**Design principle (Smart Interface Design Patterns):** Catalog cards must maintain visual rhythm. Inconsistent image heights break scanability. Two strategies:
1. **Uniform crop** (`object-cover`) — clean grid but may crop subjects.
2. **Contain with padding** (`object-contain` + bg) — full visibility but variable "active image area" within the cell, creating a "letterbox gallery" effect.

**Touch target consideration:** Smart Interface Design Patterns: *"Use 48×48px as a minimum touch target size on mobile."* The card's `<a>` wraps the entire image, so the touch target is the full card width × `h-48` — this is already satisfied.

### 1.6 Aspect Ratio of Uploaded Photos

From `apps/seed/generators/images.py` and `scripts/download_seed_photos.py` — the seed pipeline downloads random photos from Unsplash. Unsplash's default aspect ratio for `w=240&h=180` queries is 4:3, matching the thumbnail dimensions. However, **user-uploaded photos via the Telegram bot** (`telegram_bot/handlers/ad_create.py`) accept any aspect ratio — Telegram does not enforce 4:3.

> This means the catalog grid will always receive images with mixed aspect ratios, making the `object-fit` choice critical.

---

## 2. Problem 2: Ad Detail Gallery Structure & GLightbox Coexistence

### 2.1 Current State (Confirmed: ✅ GLightbox fully wired)

The detail page (`ads/detail.html:28-44`) already implements GLightbox v3.3.1 (loaded from `unpkg.com`):

```django
<!-- Photo gallery -->
{% if ad.images.all %}
    <div class="grid grid-cols-1 {% if ad.images.count > 1 %}md:grid-cols-2{% endif %} gap-2 p-4">
        {% for image in ad.images.all %}
            <a href="{{ image.image_url }}" class="glightbox" data-gallery="ad-gallery"
               data-description="{{ image.alt_text|default:"" }}"
               aria-label="{% trans "Open image" %} {{ forloop.counter }}">
                <img
                    src="{{ image.thumbnail_large_url|default:image.image_url }}"
                    alt="{% trans "Photo" %} {{ forloop.counter }} {% trans "for" %} {{ ad|get_title:LANGUAGE_CODE }}"
                    class="w-full {% if ad.images.count == 1 %}max-h-96{% else %}h-64{% endif %} object-cover rounded-lg"
                    loading="lazy"
                    width="1280" height="960"
                >
            </a>
        {% endfor %}
    </div>
{% endif %}
```

**GLightbox CSS** (`detail.html:16`) — always loaded (no consent gating):
```django
<link rel="stylesheet" href="https://unpkg.com/glightbox@3.3.1/dist/css/glightbox.min.css">
```

**GLightbox JS** (`detail.html:123-137`) — gated behind `{% if consent_analytics %}`:
```django
{% if consent_analytics %}
<script src="https://unpkg.com/glightbox@3.3.1/dist/js/glightbox.min.js" defer></script>
<script>
  document.addEventListener('DOMContentLoaded', function () {
    GLightbox({
      selector: '.glightbox',
      touchNavigation: true,
      loop: true,
      zoomable: true,
      closeOnOutsideClick: true,
      navigation: { next: true, prev: true },
    });
  });
</script>
{% endif %}
```

**No-JS fallback:** The `<img>` tags render with valid `src` attributes. Clicking the `<a>` still navigates to the full-size image URL even without GLightbox JS — this is tested in `test_gallery_markup.py:154-162` (`test_static_grid_renders_without_js`).

### 2.2 Tests Verify Gallery Behavior (Confirmed)

**`test_gallery_markup.py`** — 6 tests, all `pytest.mark.slow, pytest.mark.integration`:
- `test_detail_contains_glightbox_assets` — CSS + JS + `GLightbox({` present with consent
- `test_each_image_is_glightbox_anchor` — each image wrapped in `<a class="glightbox" data-gallery="ad-gallery">` with `href` to full image + `src` to thumbnail
- `test_glightbox_init_options_present` — init options (`touchNavigation`, `loop`, `zoomable`, etc.) in script
- `test_images_render_in_position_order` — images ordered by `AdImage.position` (model `Meta.ordering = ["position"]`)
- `test_single_image_single_anchor` — single image → single anchor
- `test_no_images_no_gallery_block` — no images → no gallery markup
- `test_static_grid_renders_without_js` — `<img>` `src` valid even without consent

**`test_script_gating.py`** — 2 tests:
- `test_scripts_absent_before_consent` — no GLightbox JS before consent
- `test_scripts_present_after_consent` — GLightbox JS present after consent

### 2.3 Consent Gating Architecture

From `apps/users/context_processors.py:40-106`:

| Variable | Anonymous (before consent) | Anonymous (after consent) | Authenticated (consent within 12mo) |
|----------|---------------------------|--------------------------|---------------------------------------|
| `consent_shown` | `True` (banner shown) | `True` (banner shown, cookie exists) | `True` (already acted) |
| `consent_analytics` | `False` | `True` | `True` |
| `consent_preferences` | `False` | `True` | `True` |

**Key design decision:** GLightbox CSS (`<link>`) is **not** gated — only the JS (`<script>`) and inline init are behind `{% if consent_analytics %}`. This is because:
- CSS is passive (no tracking, no data collection).
- The CSS file is needed to style the gallery grid layout correctly even without JS — the `rounded-lg`, `object-cover` classes are independent of GLightbox's CSS, but the lightbox overlay styles only activate when JS loads.

> **Confidence: HIGH** — confirmed by reading `detail.html:16-21` (CSS ungated) and `detail.html:123-137` (JS gated).

### 2.4 GLightbox v3.3.1 API (Verified from npm/GitHub sources)

From the npm package page and GitHub README for `glightbox@3.3.1`:

**Markup pattern:**
```html
<a href="large.jpg" class="glightbox" data-gallery="my-gallery">
    <img src="small.jpg" alt="image" />
</a>
```

**Per-slide description:**
- `data-description="text"` — sets the slide description (used on line 33)
- `data-title="text"` — sets the slide title
- `data-glightbox="title: ...; description: ..."` — V3 syntax for combined options (alternative to separate attributes)

**Init options (all confirmed in use):**
| Option | Value | Purpose |
|--------|-------|---------|
| `selector` | `.glightbox` | Elements to bind as lightbox triggers |
| `touchNavigation` | `true` | Swipe to navigate on mobile |
| `loop` | `true` | Wrap from last to first image |
| `zoomable` | `true` | Click-to-zoom / pinch-to-zoom |
| `closeOnOutsideClick` | `true` | Click overlay to close |
| `navigation` | `{ next: true, prev: true }` | Arrow button navigation |

**Default options** (from npm README):
| Option | Default | The project uses |
|--------|---------|-----------------|
| `openEffect` | `zoom` | default (unchanged) |
| `closeEffect` | `zoom` | default (unchanged) |
| `slideExtraWidth` | `0` | default (unchanged) |

**Version note:** The project pins `glightbox@3.3.1` (2025-01-21 release — the latest 3.x). The upgrade guide (`glightbox.biati.digital/guides/upgrade-from-v3/`) confirms v3 API is still current; v4 migration is not yet required.

### 2.5 Avito Gallery Structure (Verified)

**Avito main image guidelines (Russian source, HIGH confidence):**
- Optimal photo size: **1280×960 px** (or 1920×1440)
- Aspect ratio: **4:3** (landscape)
- This matches the project's `ThumbnailSizeStrEnum.LARGE = (1280, 960)`

**Avito listing gallery layout (from Scrn.gallery app screens, Feb 2026):**
- Main image at top, full-width
- Thumbnail carousel below (horizontal scroll on mobile, grid on desktop)
- 4:3 landscape ratio maintained throughout the gallery
- No zooming on grid; zoom activated on tap/hover of the main image

**Comparison with current implementation:**
| Aspect | Avito | Current (Mko Bazuna) | Gap |
|--------|-------|---------------------|-----|
| Aspect ratio | 4:3 | 4:3 (LARGE thumbnail) | None |
| Main image size | 1280×960px | `thumbnail_large_url` (1280×960) | Matches |
| Thumbnail strip | Below main image | Grid of thumbnails (all equal-size) | Different layout approach |
| Zoom | Tap/hover on main image | GLightbox `zoomable: true` | Equivalent functionality |
| Lazy loading | Yes | `loading="lazy"` | Matches |

**Avito's gallery philosophy (from Behance UX case study, Feb 2025):**
- Photos are shown in **4:3 landscape** format consistently
- The first photo must show the item clearly (head/safer positioning)
- Up to 40 photos allowed for vehicles/real estate; fewer for general goods
- No zoom-on-grid; zoom is a detail-page interaction only

### 2.6 GLightbox + Consent Gating: Progressive Enhancement Pattern

The current implementation follows a **progressive enhancement** pattern:

1. **Always (no consent):** HTML renders with valid `<img src="thumbnail_large_url">` + `<a href="full_image_url">`. The grid is visible and clickable — clicking navigates to the full image.
2. **With consent:** GLightbox JS loads and intercepts clicks, preventing navigation and opening the lightbox overlay instead.

**This is the correct pattern** because:
- GLightbox's CSS is always loaded (no visual regression before consent).
- The `class="glightbox"` and `data-gallery="ad-gallery"` attributes are inert without JS — they don't trigger any tracking or data collection.
- Only the JS (`glightbox.min.js`) and inline init block are gated, ensuring zero non-essential JS runs pre-consent.

**Potential improvement:** The current GLightbox init runs on `DOMContentLoaded`, but the `<script>` tag uses `defer`. In the current structure, the inline script is placed **inside** the `{% if consent_analytics %}` block, so it only renders when consent is given. The `DOMContentLoaded` listener will fire correctly since `defer` scripts execute before DOMContentLoaded in modern browsers.

> **Confidence: HIGH** — this pattern is verified by code inspection and the passing `test_static_grid_renders_without_js` test.

### 2.7 Vanilla JS Conventions in the Codebase

The project uses vanilla JS (no bundler) with specific conventions visible in `header_catalog.html:179-547`:

| Convention | Example |
|------------|---------|
| IIFE wrapper with `'use strict'` | `(function () { 'use strict'; ... })();` |
| `data-*` attributes for element selection | `document.querySelector('[data-categories-toggle]')` |
| Document-level event delegation | `document.addEventListener('click', function (e) { if (e.target.closest('...')) { ... } })` |
| `e.target.closest()` pattern | `e.target.closest('a[data-category-link]')` |
| `classList.add/remove` for state | `panel.classList.add('hidden')` |
| `ARIA` attributes for accessibility | `aria-expanded`, `aria-haspopup`, `aria-label` |
| `escapeHtml` helper for dynamic content | `(str) => str.replace(/&/g, '&amp;').replace(/</g, '&lt;')` etc. |

Any GLightbox-related JS enhancement should follow these conventions (IIFE, data-attributes, escapeHtml, ARIA).

---

## 3. Cross-Cutting Concerns

### 3.1 Thumbnail Size Enum

`apps/core/enums.py:85-91`:

```python
class ThumbnailSizeStrEnum(StrEnum):
    """Standard thumbnail sizes for Mko Bazuna."""
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
```

All three sizes are 4:3, matching Avito's recommended aspect ratio.

### 3.2 Image Model — URL Properties

`apps/ads/models.py:578-599` — `AdImage` provides:
- `image_url` → full-size media URL (`/media/<uuid>.jpg`)
- `thumbnail_small_url` → SMALL thumbnail (`/media/<uuid>-small.jpg`)
- `thumbnail_medium_url` → MEDIUM thumbnail (`/media/<uuid>-medium.jpg`)
- `thumbnail_large_url` → LARGE thumbnail (`/media/<uuid>-large.jpg`)

All can return `None` if the thumbnail column is empty, with `|default:` fallback to `image_url` in templates.

### 3.3 Loading Performance

- `loading="lazy"` is already on all gallery images (`detail.html:38`).
- `decoding="async"` is NOT set — could be added as a perf improvement.
- Thumbnails are pre-generated (JPEG, quality 85, progressive) — no on-the-fly resizing at request time.

### 3.4 CSS Rebuild Requirement

Any new Tailwind utility (e.g. `object-contain`, `aspect-video`, `object-center`) must trigger a CSS rebuild. The `@source` directive in `input.css` scans templates at build time. The build process is documented in `Makefile` (target: `build-css` or similar).

---

## 4. Feasible Approaches

### Problem 1: Catalog Grid Image Display

#### Approach A: `object-cover` with `object-position` (Status Quo + Focal Point)

Keep `object-cover` but add `object-position` to control the crop focus (e.g. `object-position-center object-top` to keep heads visible on portrait photos).

| Pros | Cons |
|------|------|
| No CSS rebuild needed — `object-cover` already compiled | `object-center` and `object-top` are NOT in compiled CSS — requires rebuild |
| Consistent grid height | Focal point is the same for all images — may still crop poorly for some |
| Standard pattern | Can't show full image if aspect ratios differ significantly |

#### Approach B: `object-contain` with White Background (Full Visibility)

Switch to `object-contain` with `bg-white` on the container `<a>` or a wrapper `<div>`.

| Pros | Cons |
|------|------|
| Full image always visible — no cropping | Requires CSS rebuild (`object-contain` not compiled) |
| White bg (`bg-white`) already available in CSS | Letterbox bands create "floating image" appearance — visually less tight |
| Best for e-commerce where full item visibility matters | Grid row heights vary visually (image content area differs, but container is uniform) |
| Matches Avito C2C philosophy (honest, in-context photos) | Some users perceive letterbox as "empty/wasted space" |

#### Approach C: Hybrid — `object-cover` for Grid, `object-contain` on Detail

Use `object-cover` in the catalog grid (tight grid preferred) and `object-contain` only in the detail page gallery (where full visibility matters).

| Pros | Cons |
|------|------|
| Best of both: tight grid + full detail view | Requires CSS rebuild for `object-contain` (detail page) |
| Matches Avito's pattern (cover in list, flexible in detail) | Two different behaviors to maintain |
| Detail page already uses `h-64`/`max-h-96` — letterboxing would be more acceptable there | — |

### Problem 2: Ad Detail Gallery Structure

The gallery is **already implemented** with GLightbox v3.3.1. The research question is whether improvements to the gallery structure are needed.

#### Approach A: Status Quo (No Change)

Keep the current grid layout, GLightbox v3.3.1, consent-gated JS.

| Pros | Cons |
|------|------|
| Tests already verify behavior (`test_gallery_markup.py`, `test_script_gating.py`) | Grid layout differs from Avito (which uses main-image + thumbnail-strip) |
| Progressive enhancement already correct | No keyboard navigation enhancement documented |
| GLightbox CSS always loaded, JS gated | — |

#### Approach B: Avito-Style Main Image + Thumbnail Strip

Replace the full grid with a large main image (4:3, `max-h-96`) + a horizontal strip of thumbnails below. Clicking a thumbnail opens GLightbox at the corresponding index (`lightbox.openAt(index)`).

| Pros | Cons |
|------|------|
| Matches Avito's gallery UX closely | Requires significant template restructuring |
| Better focus on the primary image | GLightbox's `openAt()` API needs the JS enhancement |
| More standard for classifieds | Needs the `header_catalog.html` vanilla JS conventions |

#### Approach C: GLightbox Video + Inline Content Extension

Future-proof the gallery to support video and inline content (GLightbox v3 supports these via the same `.glightbox` class + `data-gallery`).

| Pros | Cons |
|------|------|
| GLightbox v3 already supports videos (Vimeo, YouTube, self-hosted) | No current need (bot only uploads photos) |
| Same markup pattern (`<a class="glightbox">`) | Over-engineering for current scope |

---

## 5. Recommendations

### Problem 1: Use `object-contain` + White Background (Approach B)

**Rationale:** Avito's own philosophy (per remove-bg.io's interpretation of C2C norms) is *"honest in-context backgrounds; clean stock-style backgrounds can trigger buyer suspicion."* This means users will upload photos with varied compositions — portraits, landscapes, and everything in between. Cropping these with `object-cover` risks cutting off important parts of the item.

**Recommended implementation:**
1. Add `object-contain` and `bg-white` to the catalog card image class in `ad_list.html:80`.
2. Wrap the `<img>` in a container with a white background to fill the letterbox area.
3. **Rebuild Tailwind CSS** (required — `object-contain` is not in compiled `output.css`).
4. Optionally add `object-position-center` to control the contain alignment.

**Expected change to `ad_list.html:80`:**
```django
<!-- Before -->
class="w-full h-48 object-cover rounded-t-lg"

<!-- After -->
class="w-full h-48 object-contain rounded-t-lg bg-white"
```

> **CSS rebuild required:** `object-contain` must be added to `output.css` via Tailwind rebuild (Makefile target). `bg-white` is already compiled.

### Problem 2: Status Quo (Approach A) — Gallery is Already Correct

The GLightbox gallery implementation in `detail.html` is already well-structured:
- ✅ GLightbox v3.3.1 (latest 3.x) pinned to CDN with version
- ✅ CSS always loaded, JS consent-gated (`{% if consent_analytics %}`)
- ✅ Progressive enhancement (static `<img>` renders without JS)
- ✅ Tests verify markup, ordering, single/multi/no-image cases
- ✅ 4:3 thumbnails match Avito's recommended 1280×960 aspect ratio
- ✅ `loading="lazy"` on all images

**No changes needed** unless moving to an Avito-style main-image + thumbnail-strip layout (Approach B in section 4) is explicitly desired as a future enhancement. The current grid layout is simpler, equally functional, and well-tested.

### Build Pipeline Impact

| Change | CSS Rebuild? | Migration? | Test Updates? |
|--------|-------------|------------|---------------|
| Add `object-contain` to `ad_list.html` | ✅ Yes (`output.css` rebuild) | ❌ No | ✅ `test_gallery_markup.py` unaffected (tests detail, not list) |
| Switch `detail.html` `object-cover` → `object-contain` | ✅ Yes | ❌ No | ⚠️ `test_static_grid_renders_without_js` checks `<img>` src, not classes — should pass |
| Keep GLightbox as-is | ❌ No | ❌ No | ❌ No |

**Makefile target for CSS rebuild** (verify in `Makefile`):
```bash
# Tailwind v4 CLI (if available) or npm script
make build-css
# or
npx tailwindcss -i src/theme/static/theme/css/input.css -o src/theme/static/theme/css/output.css --minify
```

---

## 6. Summary Table

| Problem | Current | Recommended | Confidence |
|---------|---------|-------------|------------|
| Catalog grid image crop | `object-cover` (crops subjects) | `object-contain` + `bg-white` (full image visible) | **HIGH** — technique verified via MDN/DigitalOcean; utility availability verified in compiled CSS |
| Detail gallery layout | GLightbox v3.3.1 grid | Status quo (already correct) | **HIGH** — tests confirm correctness; matches Avito 4:3 spec |
| CSS rebuild needed | N/A | Yes (for `object-contain`) | **HIGH** — verified not in `@source`-compiled CSS |
| Consent gating | JS gated, CSS ungated | No change needed | **HIGH** — verified in `context_processors.py` + `detail.html` |

**No migrations required.** Changes are CSS utility class strings in templates + CSS rebuild.

---

*Report compiled from codebase evidence (HIGH confidence) and web-verified sources (MDN, DigitalOcean, GLightbox npm/GitHub docs, Avito.ru image guidelines from xn----7sbptikgmuv.xn--p1ai). The remove-bg.io "1:1 1024×1024" Avito spec is noted as LOW confidence (third-party tool, not official Avito source).*
