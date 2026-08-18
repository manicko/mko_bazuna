# Specification: Ad Detail Page Image Gallery

**ID:** 013  
**Type:** Enhancement  
**Source Decision:** Decision_015.md  
**Status:** Approved  
**Product Owner Decisions:** Q1=A, Q2=A, Q3=A, Q4=A, Q5=A, Q6=A, Q7=A, Q8=A  

---

## 1. Purpose

Replace the static image grid on the ad detail page (`ads/detail.html`) with a modern fullscreen image gallery so buyers can browse the 1–5 photos of an ad in an immersive overlay.

## 2. Scope

### In Scope
- Buyer-facing ad detail page (`/ads/<slug>/`).
- Client-side gallery for existing `AdImage` instances.

### Out of Scope
- Image upload, thumbnail generation.
- Admin-side photo moderation.
- Ad listing page images.
- `AdImage` model, database schema, or migrations.
- New Django package dependencies.

## 3. Requirements

### Functional

FR-01: Clicking any ad image opens a fullscreen modal overlay with the full-sized image.
FR-02: The modal contains prev/next navigation arrows.
FR-03: The modal displays an image counter (e.g., "2 / 5").
FR-04: A dark semi-transparent backdrop sits behind the modal.
FR-05: Clicking outside the image or pressing ESC closes the modal.
FR-06: Full keyboard navigation: left/right arrows, ESC, Tab.
FR-07: Mobile touch swipe for navigation.
FR-08: Zoom: pinch-to-zoom on mobile, click-drag panning on desktop.
FR-09: Thumbnail strip inside the modal for direct jumping.
FR-10: Images displayed in `AdImage.position` order.
FR-11: No new Django models/fields/migrations.

### Non-Functional

NFR-01: Library — GLightbox v3.3.1 (MIT, 0 deps, ~15KB gzipped), CDN-loaded.
NFR-02: No new Django packages. Inline IIFE script pattern.
NFR-03: CSP — `script-src` allows `https://unpkg.com`; `style-src` permits inline styles from GLightbox.
NFR-04: Accessibility — WCAG 2.1 AA compliance (ARIA, focus trap, keyboard nav).
NFR-05: Progressive enhancement — static grid remains functional without JS.
NFR-06: Tailwind compatibility — no conflicts with committed `output.css`.

## 4. Assumptions

A1: "Free" = open-source, client-side, CDN-loadable, no build system.
A2: Gallery opens on image click only.
A3: Modal uses `thumbnail_large` or `image` URL via `media_gate` — existing fallback logic applies.
A4: Static image grid is the trigger; no structural change to grid itself.

## 5. Library Selection

**Selected: GLightbox v3.3.1** — MIT license, 0 dependencies, ~15KB gzipped, CDN available.

| Feature        | GLightbox | PhotoSwipe | baguetteBox | Custom JS |
|----------------|-----------|------------|-------------|-----------|
| Zoom           | Yes       | Yes        | No          | Yes (complex) |
| Swipe          | Yes       | Yes        | Yes         | Yes       |
| Keyboard       | Yes       | Yes        | Yes         | Yes       |
| ARIA           | Yes       | Yes        | Limited     | Yes       |
| Size           | ~15KB     | ~17KB      | ~3KB        | 100+ lines|

## 6. Technical Approach

### 6.1 Data Model

No changes. Uses existing `AdImage`:

```python
class AdImage(models.Model):
    ad = ForeignKey(Ad, related_name="images")
    image = ImageField(...)
    thumbnail_small = ImageField(...)   # 240x180
    thumbnail_medium = ImageField(...)  # 640x480
    thumbnail_large = ImageField(...)   # 1280x960
    position = PositiveSmallIntegerField(...)
    sha256 = models.CharField(...)
```

URLs served via `media_gate` at `/media/<image_key>` with PUBLISHED-status access control.

### 6.2 Existing Template (Target)

`src/backend/templates/ads/detail.html` lines 31–44 — static image grid. No JS currently loaded on this page.

## 7. Implementation Tasks

### Task 1: Add CDN Links

**File:** `src/backend/templates/ads/detail.html`

In `<head>`:
```html
<link rel="stylesheet" href="https://unpkg.com/glightbox@3.3.1/dist/css/glightbox.min.css">
```

Before `</body>`:
```html
<script src="https://unpkg.com/glightbox@3.3.1/dist/js/glightbox.min.js" defer></script>
```

### Task 2: Add Gallery Attributes to Image Links

**File:** `src/backend/templates/ads/detail.html`, lines 31–44

```html
{% for image in ad.images.all %}
<a href="{{ image.image_url }}" class="glightbox" data-gallery="ad-gallery" data-description="{{ image.alt_text|escape }}">
  <img src="{{ image.thumbnail_large_url }}" alt="{{ image.alt_text|default:'' }}" loading="lazy" class="...">
</a>
{% endfor %}
```

- `href` → full image URL (loaded in modal).
- `class="glightbox"` → GLightbox selector target.
- `data-gallery="ad-gallery"` → groups images for navigation.
- `data-description` → sets caption from alt text.

### Task 3: Initialize GLightbox

**File:** `src/backend/templates/ads/detail.html`

Inline `<script>` after GLightbox JS:

```html
<script>
  document.addEventListener('DOMContentLoaded', function () {
    GLightbox({
      selector: '.glightbox',
      touchNavigation: true,
      loop: true,
      zoomable: true,
      counter: { text: '{{counter}} / {{total}}' },
      closeOnOutsideClick: true,
      navigation: { next: true, prev: true },
    });
  });
</script>
```

## 8. Acceptance Criteria

AC-01: Clicking any image opens GLightbox modal with full image.
AC-02: Modal shows counter (e.g., "1 / 5").
AC-03: Arrow buttons/keypresses navigate prev/next (ordered by position).
AC-04: Backdrop click or ESC closes modal.
AC-05: Mobile swipe navigates images.
AC-06: Pinch-to-zoom / click-drag panning works.
AC-07: Thumbnail strip visible; clicking jumps to image.
AC-08: Keyboard nav (arrows, ESC, Tab) works.
AC-09: ARIA attributes present on modal.
AC-10: No server errors or broken image links.
AC-11: No CSP violation errors in console.
AC-12: Static grid still works without JS.

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| CDN outage | Graceful degradation to static grid |
| CSP violation (inline styles) | `style-src` must include `'unsafe-inline'` — update `base.py` if needed |
| Focus trap failure | Use GLightbox `focusable: true` + `aria-modal` — test keyboard |
| Mobile zoom conflict | GLightbox sets `touch-action: none` during interaction |
| SRI hash mismatch | Generate hash from actual CDN resource at implementation |

## 10. Verification Plan

1. Desktop: open modal, test arrows/ESC/counter/zoom/backdrop/thumbnail click.
2. Mobile: test swipe, pinch-zoom, tap-away.
3. No-JS: verify static grid visible, no errors.
4. CSP: check browser console for report-only violations.
5. Accessibility: Lighthouse audit for keyboard nav, ARIA, contrast.
6. Django: run `uv run pytest` on existing ad detail tests — confirm no regressions.

## 11. References

- Source decision: `.ai/problems/Decision_015.md`
- Ad model: `src/backend/apps/ads/models.py`
- Detail view: `src/backend/apps/ads/views/listings.py`
- media_gate view: `/media/<path:image_key>`
- Settings/CSP: `src/backend/config/settings/base.py`
- Tailwind pipeline: committed `output.css` via `@import "tailwindcss"`
- Research: `.ai/research/lightbox-library-comparison.md`, `.ai/research/js-css-pipeline.md`

## 12. Post-Approval Open Questions

OQ-01: Should the gallery support video for AdImage entries? → Out of scope (image-only currently).
OQ-02: Should "Download original" be a feature? → Not requested.
OQ-03: Should the gallery pre-fetch next image? → GLightbox handles natively.