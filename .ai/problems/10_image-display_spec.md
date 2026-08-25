# Problem Spec 10: Image Display — Crop/Stretch on Catalog Grid and Missing Slider on Detail Page

**Spec ID:** 10  
**Created:** 2026-08-24  
**Status:** Approved (PO decisions collected)  
**Source:** Catalog grid images appear cropped/stretched due to `object-cover`; detail page lacks a thumbnail-strip slider.  
**Spec index:** [docs/01-spec/spec-index.md](docs/01-spec/spec-index.md)  

---

## 1. Problem Statement

Two image-display defects across two user-facing surfaces:

1. **Catalog grid (`ad_list.html`):** Images rendered with `class="object-cover"` are cropped and stretched. Product photos — which may have arbitrary aspect ratios from Telegram compression — are forced into a 240×180 (4:3) box, clipping important content. Users cannot see the full product in the thumbnail.

2. **Ad detail page (`detail.html`):** There is no dedicated slider/gallery component. Images are rendered as a static grid (`grid grid-cols-1 md:grid-cols-2`) with GLightbox anchors for fullscreen viewing only. There is no main-image preview with arrow navigation, no horizontal thumbnail strip, and no click-to-zoom on the thumbnails themselves. The UX falls short of the Avito-style pattern the product requires.

---

## 2. Confirmed Facts

| # | Fact | Evidence (file:line) |
|---|------|---------------------|
| F1 | Catalog grid uses `object-cover` on a fixed `h-48` container (240×180 target). | `ads/partials/ad_list.html:80` |
| F2 | `ThumbnailService.SIZES` defines SMALL=(240,180), MEDIUM=(640,480), LARGE=(1280,960) — all are **aspect-ratio-constrained crops** that fit to exact dimensions. | `media/services/thumbnails.py:30-37` |
| F3 | The `ImageGenerator` (seed) and `backfill_thumbnails.py` both use `ThumbnailService.resize` which crops to exact size, not letterbox. | `seed/generators/images.py`, `media/management/commands/backfill_thumbnails.py` |
| F4 | Detail page uses GLightbox v3.3.1 (CDN via unpkg) with inline init; anchors have `class="glightbox"` and `data-gallery="ad-gallery"`. | `ads/detail.html:16,124-136` |
| F5 | Detail gallery is a static CSS grid (`grid-cols-1 md:grid-cols-2`), not a slider. Each image is a `glightbox` anchor wrapping a `thumbnail_large_url` thumbnail. | `ads/detail.html:29-43` |
| F6 | GLightbox init includes `zoomable: true`, `touchNavigation: true`, `loop: true`, `navigation: { next, prev }`. | `ads/detail.html:127-134` |
| F7 | GLightbox JS/CSS are gated behind `consent_analytics` (D7 / T-06b). Scripts only render after user accepts analytics consent. | `ads/detail.html:119-137`, `test_script_gating.py` |
| F8 | GLightbox is a single CDN source (unpkg), loaded as classic `<script>`/`<link>`, not ESM. | `ads/detail.html:16,124` |
| F9 | `AdImage` model has `thumbnail_small`, `thumbnail_medium`, `thumbnail_large`, and `image` fields. URL properties: `thumbnail_small_url`, `thumbnail_large_url`, `image_url`. | `ads/models.py:498-599` |
| F10 | `AdImage` model has **no** `width`/`height` pixel dimension fields. | `ads/models.py:498-599` |
| F11 | Seed image constraints: `max_dimension_px=1080`, `jpeg_quality=75`, `max_image_size_bytes=100000`. | `scripts/seed-images-config.json` |
| F12 | GLightbox v3.3.1 supports a thumbnail strip via the `pager` option, but this requires `data-gallery` configuration per-anchor and is not currently used. | GLightbox docs (researcher-confirmed) |
| F13 | CSP is report-only (no enforcement); unpkg CDN is already allowlisted. | `ads/detail.html:15` |
| F14 | Existing tests: `test_gallery_markup.py` asserts GLightbox CSS/JS/init presence, anchor structure, image order, single/no-image branches, and no-JS fallback. `test_script_gating.py` asserts GLightbox scripts absent before consent, present after. | `ads/tests/test_gallery_markup.py`, `ads/tests/test_script_gating.py` |
| F15 | `ThumbnailService` uses `ImageOps.fit()` which crops to exact dimensions, not letterbox. | `media/services/thumbnails.py` |

---

## 3. Root Cause

### Problem 1: Catalog grid crop/stretch

The `ThumbnailService.resize` method (used by both the seed image generator and the backfill command) crops thumbnails to exact `width × height` dimensions using Pillow's `ImageOps.fit()`, which centers and crops. The catalog grid then applies `object-cover` to that already-cropped 240×180 thumbnail inside an `h-48` container. The result is a double-crop: the thumbnail generation crops non-4:3 source images, and `object-cover` crops again in the browser. Important visual content is lost.

### Problem 2: No slider on detail page

The detail page template was built as a simple grid of GLightbox anchors. There was never a requirement for a main-image + thumbnail-strip slider pattern. The current design relies entirely on GLightbox's fullscreen overlay for navigation (arrows, swipe, zoom). There is no in-page thumbnail strip, no main-image selection via thumbnails, and no click-to-zoom without entering the GLightbox overlay.

---

## 4. Research Findings (Splide + PhotoSwipe Evaluation)

**Delegated to Researcher agent. Decision: Do NOT adopt Splide + PhotoSwipe.**

| Library | JS (gzipped) | CSS (gzipped) | CDN |
|---|---|---|---|
| GLightbox v3.3.1 (current) | 15.1 KB | 2.5 KB | unpkg |
| Splide v4.1.4 (core) | 12.7 KB | 0.7 KB | jsdelivr |
| PhotoSwipe v5.4.4 (lightbox + core) | 4.5 KB + 16.3 KB | 1.4 KB | cdnlib |
| **Splide + PhotoSwipe combined** | **17.2 KB initial + 16.3 KB lazy = 33.5 KB** | **2.1 KB** | **2 CDNs** |

**Decision: Do NOT proceed with Splide + PhotoSwipe.**

**Blockers:**
1. **2.1× heavier** than current GLightbox (36.2 KB vs 17.6 KB total).
2. **PhotoSwipe requires `data-pswp-width`/`data-pswp-height`** on every image anchor — `AdImage` has no dimension fields (F10), requiring either a DB migration + bot-side dimension capture, or a JS workaround.
3. **Two CDN providers** (jsDelivr + cdnlib) vs current single unpkg.
4. **ES module friction** — PhotoSwipe's primary distribution is ESM (`type="module"`), but the project uses plain `<script>` tags; UMD builds are under-documented.
5. **No built-in zoom in Splide v4** — the v3 Zoom extension was dropped/renamed to `xZoom`; pinch-zoom needs an external library.
6. **Test rewrite required** — `test_gallery_markup.py` and `test_script_gating.py` assert specific GLightbox class names, init options, and CDN URLs.

**Recommended alternative:** Enhance GLightbox in place with a pure CSS/Tailwind thumbnail strip + minimal Vanilla JS for thumbnail/arrows switching. No new dependencies, no model changes, no ESM adoption.

---

## 5. Confirmed Requirements

| Req ID | Requirement | Source |
|--------|-------------|--------|
| REQ-10.1 | Catalog grid thumbnails must display the full image content without cropping or stretching, with empty space filled in white. | PO instruction |
| REQ-10.2 | The white-fill must be applied via CSS styles, not by padding images at generation time. | PO instruction (F15) |
| REQ-10.3 | Catalog images must preserve their original aspect ratio within the thumbnail container. | UX consistency |
| REQ-10.4 | The ad detail page must display a main image preview with a horizontal thumbnail strip below it. | Avito pattern reference |
| REQ-10.5 | Clicking a thumbnail in the strip must update the main image preview. | Standard gallery UX |
| REQ-10.6 | Arrow navigation (prev/next) must be available on the main image preview. | Avito pattern reference |
| REQ-10.7 | Clicking the main image must open the GLightbox fullscreen overlay (preserving existing zoom/swipe/arrow behavior). | Preserve current behavior |
| REQ-10.8 | The thumbnail strip must scroll horizontally on viewports where all thumbnails don't fit. | Mobile-first, Avito pattern |
| REQ-10.9 | Progressive enhancement: with JavaScript disabled, the no-JS fallback must still render valid image thumbnails. | AGENTS.md principle + existing test coverage |
| REQ-10.10 | No new JavaScript libraries may be introduced. | Researcher recommendation + AGENTS.md principle #5 |
| REQ-10.11 | No database schema changes (no new fields on `AdImage`). | Researcher blocker for PhotoSwipe |
| REQ-10.12 | All user-visible strings must be wrapped in `{% trans %}` / `{% blocktrans %}`. | AGENTS.md principle #16 |
| REQ-10.13 | GLightbox script gating behind `consent_analytics` must be preserved. | F7, `test_script_gating.py` |
| REQ-10.14 | When the main image changes via thumbnails or arrows, the GLightbox anchor href must be updated to match the currently displayed image, so fullscreen opens the correct image. | PO proposal — href synchronization |

---

## 6. Conceptual Tasks

### Task 1: Fix catalog grid image display (Problem 1)

**Objective:** Replace `object-cover` with `object-contain` on catalog grid thumbnails, and add CSS to fill empty space with white.

**Changes:**

1. **`ads/partials/ad_list.html:80`** — Replace `object-cover` with `object-contain` and add a white background to the image element:
   - Current: `class="w-full h-48 object-cover rounded-t-lg"`
   - New: `class="w-full h-48 object-contain bg-white rounded-t-lg"`
   - The `bg-white` fills the padded area with white, achieving the PO's instruction of white-fill via CSS.

2. **No changes to `ThumbnailService`** — The PO explicitly states CSS-only fix. The thumbnails remain 240×180 crops, but `object-contain` will display the full cropped thumbnail centered within the `h-48` container with white padding where the aspect ratio doesn't match. **Note:** if the source image is non-4:3, the thumbnail itself is already cropped by `ImageOps.fit()` — the PO accepts this, wanting only the browser-level presentation fixed.

3. **Update tests** — If a catalog grid test exists, it should assert `object-contain` is present (not `object-cover`).

**Files:** `ads/partials/ad_list.html`

### Task 2: Add thumbnail-strip slider to detail page (Problem 2)

**Objective:** Replace the static grid with a main-image + horizontal-thumbnail-strip slider using **Vanilla JS + Tailwind CSS**, keeping GLightbox for fullscreen overlay on click.

**Changes:**

1. **`ads/detail.html:29-43`** — Rewrite the gallery block as:

   ```html
   {% if ad.images.all %}
   <div class="gallery p-4" data-detail-gallery>
       {# Main image preview with arrow nav #}
       <div class="relative mb-4">
           {% with primary=ad.images.first %}
           <a id="detail-main-link"
              href="{{ primary.image_url }}"
              class="glightbox" data-gallery="ad-gallery"
              data-description="{{ primary.alt_text|default:'' }}"
              aria-label="{% trans "Open image" %} 1">
               <img id="detail-main-image"
                    src="{{ primary.thumbnail_large_url|default:primary.image_url }}"
                    alt="{% trans "Photo" %} 1 {% trans "of" %} {{ ad|get_title:LANGUAGE_CODE }}"
                    class="w-full max-h-96 object-contain bg-gray-100 rounded-lg"
                    loading="lazy"
                    width="1280" height="960">
           </a>
           <button id="detail-prev" type="button"
                   class="absolute left-2 top-1/2 -translate-y-1/2 bg-white/80 rounded-full p-1 shadow hover:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                   aria-label="{% trans "Previous image" %}">
               <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                   <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                         d="M15 19l-7-7 7-7"></path>
               </svg>
           </button>
           <button id="detail-next" type="button"
                   class="absolute right-2 top-1/2 -translate-y-1/2 bg-white/80 rounded-full p-1 shadow hover:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                   aria-label="{% trans "Next image" %}">
               <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                   <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                         d="M9 5l7 7-7 7"></path>
               </svg>
           </button>
           {% endwith %}
       </div>
       {# Thumbnail strip #}
       <div id="detail-thumbs"
            class="flex gap-2 overflow-x-auto scroll-px-2 pb-1"
            data-detail-thumbs>
           {% for image in ad.images.all %}
           <button type="button"
                   class="flex-shrink-0 w-16 h-12 rounded overflow-hidden border-2 border-transparent hover:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                   data-index="{{ forloop.counter0 }}"
                   data-full-url="{{ image.image_url }}"
                   data-thumb-url="{{ image.thumbnail_large_url|default:image.image_url }}"
                   aria-label="{% trans "Select image" %} {{ forloop.counter }}">
               <img src="{{ image.thumbnail_small_url|default:image.image_url }}"
                    alt="{% trans "Photo" %} {{ forloop.counter }}"
                    class="w-full h-full object-cover">
           </button>
           {% endfor %}
       </div>
   </div>
   {% endif %}
   ```

2. **Add Vanilla JS inline script** — A minimal inline JS snippet (≤10 lines) maintains `activeIndex` and provides `updateMainImage(index)` which:
   - Updates `detail-main-image.src` to the thumbnail's `data-thumb-url`
   - Updates `detail-main-image.alt` to the appropriate translated alt text
   - Updates `detail-main-link.href` to the thumbnail's `data-full-url` (so GLightbox opens the correct full-size image)
   - Updates `detail-main-link.data-description` if alt_text is available
   - Thumbnail click and prev/next buttons call `updateMainImage` with the correct index
   - Image metadata (urls) is read from the `data-*` attributes on thumbnail buttons (no JSON injection needed — data attributes suffice)

3. **Preserve GLightbox integration** — The main image remains wrapped in a `glightbox` anchor with `data-gallery="ad-gallery"`. GLightbox init stays in the same `{% if consent_analytics %}` block. When a non-consenting user clicks the main image, the anchor still works as a plain link to the full-size image (progressive enhancement).

4. **Update tests** — `test_gallery_markup.py` must be updated to assert:
   - The new slider structure: `data-detail-gallery` container, `detail-main-image`, `detail-main-link.glightbox`, `detail-prev`, `detail-next`, `detail-thumbs`
   - `object-contain` on the main image (not `object-cover`)
   - `glightbox` anchor still present on the main image with `data-gallery="ad-gallery"`
   - Thumbnail buttons with `data-index`, `data-full-url`, `data-thumb-url` attributes
   - Images render in `AdImage.position` order
   - Single-image and no-image branches preserved
   - No-JS fallback: the main `<img>` still renders with valid `src`

   `test_script_gating.py` — **no changes needed** if GLightbox CDN URL stays the same (F8).

**Files:** `ads/detail.html`, `ads/tests/test_gallery_markup.py` (update)

### Task 3: Update documentation

**Objective:** Update the design-system and UI-pattern docs to reflect the new gallery pattern.

1. **`docs/01-spec/ui-patterns.md`** — Update "Image Gallery for Ad Detail Page" section (lines 149-203) to describe the new slider pattern: main image + thumbnail strip + arrow nav + GLightbox click-to-zoom.

2. **`docs/06-design-system/components.md`** — Update "Ad Card (Detail View)" section (lines 417-446) to reflect `object-contain` on catalog grid and the new slider pattern on detail.

**Files:** `docs/01-spec/ui-patterns.md`, `docs/06-design-system/components.md`

### Task 4: Update spec index

**Objective:** Link Spec 10 from the "Known Problems" table in the spec index.

1. **`docs/01-spec/spec-index.md`** — Add row to the Known Problems table.

**Files:** `docs/01-spec/spec-index.md`

---

## 7. PO Decisions (Collected)

**Decision Date:** 2026-08-24

1. **Catalog grid fix approach:** DECIDED — **CSS-only `object-contain` + `bg-white`** on the image element. No changes to `ThumbnailService` or image generation. The white-fill is achieved via CSS `bg-white` (or `bg-gray-100` for subtle contrast), not by letterboxing in Pillow. ✅ Unblocks Task 1.

2. **Detail page slider approach:** DECIDED — **Enhance GLightbox in place with a pure CSS/Tailwind thumbnail strip**. No Splide, no PhotoSwipe, no new JS libraries. Main image + horizontal scrolling thumbnail strip with arrow prev/next buttons. GLightbox handles fullscreen on click. ✅ Unblocks Task 2.

3. **Slider interaction model:** DECIDED — **Minimal inline Vanilla JS** (≤10 lines) for thumbnail click + prev/next arrow switching. No HTMX/HTTP round-trip; the thumbnail-to-main-image swap is a client-side DOM operation. Image metadata read from `data-*` attributes on thumbnail buttons. Rationale: avoids round-trips for a trivial UI interaction, no new dependencies. ✅ Unblocks Task 2.

4. **Main image display on detail:** DECIDED — **Use `object-contain`** on the detail page main image with `bg-gray-100` background for subtle off-white padding. Thumbnails in the strip use `object-cover` (small, no distortion concern at 64×48). ✅ Unblocks Task 2.

5. **GLightbox CDN:** DECIDED — **Keep GLightbox v3.3.1 on unpkg** unchanged. No version bump. ✅ Unblocks Task 2.

6. **i18n strings:** DECIDED — Wrap all new user-visible strings (`{% trans "Previous image" %}`, `{% trans "Next image" %}`, `{% trans "Select image" %}`, `{% trans "Open image" %}`, `{% trans "of" %}`) in `{% trans %}` tags. Run `make makemessages` + `make compilemessages` before committing. ✅ Applies to Tasks 2, 3.

7. **Test strategy:** DECIDED — **Update existing tests** (`test_gallery_markup.py`) rather than creating a new test file. Assert the new slider markup structure and `object-contain` class. No new test file needed. ✅ Unblocks Task 2.

8. **Slider component architecture:** DECIDED — **Vanilla JS + Tailwind CSS** (no Splide, no PhotoSwipe, no Alpine.js). Main image preview + horizontal thumbnail strip + arrow nav + GLightbox fullscreen on click. Thumbnail click and arrow buttons use a minimal inline JS snippet that maintains an `activeIndex` and updates both the main `<img src>` and the GLightbox anchor `href` atomically. Image metadata read from `data-*` attributes on thumbnail buttons (no JSON injection needed). ✅ Unblocks Task 2.

---

## 8. Assumptions

| # | Assumption | Basis |
|---|------------|-------|
| A1 | `object-contain` + `bg-white` will visually satisfy the PO by showing the full cropped thumbnail with white padding where aspect ratio doesn't match 4:3. | PO Decision §7.1 — the thumbnail itself is already cropped by `ThumbnailService`; the PO accepts this, wanting only the browser-level presentation fixed |
| A2 | Thumbnail strip images at `thumbnail_small_url` (240×180) are sufficient resolution for 64×48 thumbnail buttons. | `ThumbnailService.SIZES` SMALL=(240,180); thumbnails rendered at w-16×h-12 |
| A3 | Chevron icons can be inline SVGs (no partial file lookup needed). | Simpler than depending on `components/icons/` partials; inline SVG avoids 404 risk |
| A4 | GLightbox's built-in `data-gallery="ad-gallery"` group will correctly navigate across all images when opened from the main image, even though thumbnails are separate `<button>` elements (not `<a>` anchors). | GLightbox navigates by `data-gallery` attribute; only the main image anchor has this attribute |
| A5 | Inline JS for thumbnail switching does not violate the "HTMX MPA" architectural stance, as it is a trivial DOM operation, not a state-management concern. | PO Decision §7.3 — minimal inline JS approved |
| A6 | The `consent_analytics` gating on GLightbox scripts is unaffected by the gallery restructure, since the `<script>` and `<link>` tags remain in the same conditional block. | `ads/detail.html:119-137` structure preserved |
| A7 | `max-h-96` (384px) is the appropriate max-height for the main detail image, matching the current design. | PO did not specify a different height; consistency preferred |

---

## 9. Constraints

| # | Constraint | Source |
|---|-----------|--------|
| C1 | No new JavaScript libraries may be added (no Splide, no PhotoSwipe, no Alpine.js, no Swiper). | Researcher recommendation + AGENTS.md principle #5 |
| C2 | GLightbox CDN source (unpkg) and version (v3.3.1) must not change. | PO Decision §7.5 |
| C3 | All user-visible strings must be wrapped in `{% trans %}` / `{% blocktrans %}`. | AGENTS.md principle #16 |
| C4 | White-fill must be CSS-only, not via image generation or `ThumbnailService` changes. | PO Decision §7.1 |
| C5 | Tests require Docker PostgreSQL on port 5433; never run `uv run pytest` locally. | `.kilo/rules/commands.md` |
| C6 | Fast gate: `make test` skips `seed` marker tests. | `.kilo/rules/commands.md` |
| C7 | Templates must pass `test_i18n_completeness.py`. | AGENTS.md principle #16 / Definition of Done |
| C8 | No database migrations needed for this spec. | No schema changes |

---

## 10. Risks

| # | Risk | Mitigation |
|---|------|-----------|
| R1 | **GLightbox thumbnail navigation may not work** if the thumbnail `<button>` elements are not `<a>` anchors with `glightbox` class. GLightbox groups by `data-gallery` attribute on `glightbox` anchors only. | Ensure the main image remains a `glightbox` anchor with `data-gallery="ad-gallery"`. Thumbnails are plain `<button>` elements for switching the main image; GLightbox only activates on click of the main image. Verify in testing. |
| R2 | **Inline JS for thumbnail switching** could be flagged by linting or CSP reporting. | Keep inline JS minimal and scoped to `data-detail-gallery` attribute. CSP is report-only. Document the pattern. |
| R3 | **`test_gallery_markup.py` breakage** — existing assertions check for `class="glightbox"`, `data-gallery="ad-gallery"`, `object-cover`, and grid-based layout. The new slider pattern changes these. | Update tests to assert new structure: `object-contain` on main image, `glightbox` anchor still present, `data-detail-gallery` container, `detail-prev`/`detail-next` button IDs, `detail-thumbs` thumbnail strip. |
| R4 | **`test_script_gating.py`** may break if GLightbox `<script>` tag location changes. | Keep `<script>` and `<link>` tags in the same `{% if consent_analytics %}` block at the same location (before `</body>`). No structural change to script gating. |
| R5 | **Thumbnail strip scroll behavior** on mobile — `overflow-x-auto` may have inconsistent browser support without `-webkit-overflow-scrolling`. | Add `-webkit-overflow-scrolling: touch` via Tailwind or inline style. Test on mobile viewport. |
| R6 | **No-JS fallback** — if inline JS is disabled, prev/next and thumbnail click won't work, but the main image GLightbox anchor still functions. | The main image `<a class="glightbox">` remains a valid link to the full image. GLightbox handles fullscreen. Thumbnail strip is progressive enhancement. |
| R7 | **Image alt text / accessibility** — new buttons need proper `aria-label`s and keyboard navigation. | All buttons have `aria-label` with `{% trans %}`; `tabindex` preserved by `<button>` elements. |
| R8 | **GLightbox href synchronization** — when the main image changes via thumbnails/arrows, the GLightbox anchor `href` must be updated to match, or fullscreen opens the wrong image. | The inline JS updates both the `<img src>` and the `<a href>` on the GLightbox anchor atomically in `updateMainImage()`. Add a test assertion that the `href` matches the currently selected image. |

---

## 11. Open Questions

1. **Do the `components/icons/chevron_left.html` and `chevron_right.html` partials exist?** If they do, prefer using them; if not, use inline SVGs. — **Researcher to verify.** *(Low priority — inline SVGs are the default approach in A3.)*

---

## 12. Out of Scope

- **Changing `ThumbnailService` crop behavior** — the service will continue cropping to exact dimensions. The fix is presentation-layer only (`object-contain`).
- **Adding `width`/`height` dimension fields to `AdImage`** — not needed since we are not adopting PhotoSwipe.
- **Adopting Splide.js or PhotoSwipe** — researcher evaluation conclusively rejected this approach.
- **Server-side image resampling changes** — no changes to `ImageGenerator`, `backfill_thumbnails.py`, or `ThumbnailService`.
- **Bot-side photo handling** — the Telegram bot sends photos as-is; no changes to the bot upload flow.
- **Lazy-loading strategy changes** — existing `loading="lazy"` on `<img>` tags is preserved.
- **Touch/swipe support on the thumbnail strip** — native `overflow-x-auto` horizontal scrolling is sufficient; no custom touch handlers.

---

## 13. Definition of Ready

A task is ready to be implemented when:
1. ✅ Root cause is identified and confirmed (Section 3).
2. ✅ Research on Splide + PhotoSwipe is complete and decision is documented (Section 4).
3. ✅ All affected files are enumerated (Section 6).
4. ✅ PO decisions collected (Section 7) — **all 8 decided**.
5. ✅ Existing test baseline is green (`make test` fast gate passes).

---

## 14. Definition of Done

A task is done when:
1. ✅ Catalog grid uses `object-contain` with `bg-white` (or `bg-gray-100` per PO decision) instead of `object-cover`.
2. ✅ Detail page renders a main image preview with prev/next arrow buttons and a horizontal thumbnail strip below it.
3. ✅ Clicking a thumbnail in the strip updates the main image preview via Vanilla JS (no HTMX/HTTP round-trip).
4. ✅ Arrow buttons (prev/next) switch images via Vanilla JS.
5. ✅ Clicking the main image opens GLightbox fullscreen overlay with the full gallery.
6. ✅ All new user-visible strings are wrapped in `{% trans %}` and pass `test_i18n_completeness.py`.
7. ✅ `test_gallery_markup.py` is updated and passes with the new slider markup assertions.
8. ✅ `test_script_gating.py` passes unchanged (GLightbox gating preserved).
9. ✅ `uv run ruff check` and `uv run basedpyright` pass on all changed files.
10. ✅ `docs/01-spec/ui-patterns.md` and `docs/06-design-system/components.md` are updated.
11. ✅ `docs/01-spec/spec-index.md` links to this spec.
12. ✅ `make makemessages` + `make compilemessages` run and `.po` files updated.
13. ✅ This spec is marked `Status: Complete` and linked from the spec index.
