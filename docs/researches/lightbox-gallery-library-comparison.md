# Lightbox / Gallery Library Comparison — for Mko Bazuna (Django HTMX MPA)

**Decision context:** `src/backend/templates/ads/detail.html` currently renders 1–5 ad photos as a
static, non-interactive image grid. We need a lightbox/gallery so buyers can "scroll through pictures"
with navigation, mobile touch swipe, pinch-to-zoom, keyboard nav, and ESC-to-close — matching the
"modern gallery" UX (modal overlay, arrows, counter, gesture + keyboard).

**Project constraints (verified from source):**
- Stack: Django 5.2 + HTMX MPA (server-rendered HTML, HTMX for dynamic fragments). No React/Vue/Svelte.
- JS loading pattern: CDN `<script>` tags (see `list.html` line 15: `https://unpkg.com/htmx.org@1.9.12`).
- CSS: Tailwind built pipeline (`static/theme/css/input.css` → `output.css`). No JS bundler / node pipeline (`builders/front/package.json` is bare `{"type":"module"}`).
- Images served from R2 with `image.image_url`, `image.thumbnail_small_url`, `image.thumbnail_large_url` (see `detail.html` lines 32–43).
- Strict: no `print()`, no plain-string constants, dependency-free preferred, MIT license required.

Methodology: bundle sizes from the Bundlephobia API (exact minified/gzip bytes); CDN URLs and
installation confirmed live against jsDelivr/cdnjs/unpkg; features from each library's official docs
(Context7) and source; maintenance from npm + GitHub + libraries.io.

---

## Verified size table (JS only, minified / gzipped)

| Library | Version | Minified | Gzipped | Deps | CDN (global/UMD) |
|---|---|---|---|---|---|
| PhotoSwipe | v5.4.4 | 57 KB | 16.9 KB | 0 | `https://cdn.jsdelivr.net/npm/photoswipe@5.4.4/dist/umd/photoswipe-lightbox.umd.min.js` + core |
| GLightbox | v3.3.1 | ~54 KB | 15.0 KB | 0 | `https://cdn.jsdelivr.net/npm/glightbox@3.3.1/dist/js/glightbox.min.js` |
| baguetteBox | v1.13.0 | ~9 KB | ~3.2 KB | 0 | `https://cdn.jsdelivr.net/npm/baguettebox.js@1.13.0/dist/baguetteBox.min.js` |
| Lightbox2 | v2.11.5 | ~9 KB | 2.8 KB | **jQuery** (peer) | jquery must be added (~30 KB gzipped on top) |

> Lightbox2's own code is tiny, but it has a **hard jQuery dependency** (npm lists `jquery` as an
> ignored peer dep). The project uses no jQuery; adding it just for a gallery is a hard contradiction.

All bundles require a CSS file too (separate, small). PhotoSwipe and GLightbox also offer ESM
(`type="module"`) builds; GLightbox, baguetteBox, Lightbox2 ship a global UMD build usable with a
plain `<script>` tag — exactly the pattern already used for htmx.

---

## Feature matrix (confidence: HIGH where sourced from docs, ABSENT where docs enumerate no support)

| Criterion | PhotoSwipe v5 | GLightbox v3 | baguetteBox v1.13 | Lightbox2 v2 | Custom vanilla |
|---|---|---|---|---|---|
| License | MIT ✓ | MIT ✓ | MIT ✓ | MIT ✓ | n/a |
| Bundle (gz) | ~17 KB | ~15 KB | ~3 KB | ~3 KB + jQuery 30 KB | 0 |
| Dependencies | 0 ✓ | 0 ✓ | 0 ✓ | jQuery ✗ | 0 ✓ |
| CDN global/UMD build | ✓ (UMD) | ✓ (UMD) | ✓ (UMD) | ✓ (UMD) | n/a |
| Touch swipe nav | ✓ | ✓ | ✓ | ✗ (none) | impl. effort |
| Pinch-to-zoom + pan | ✓ (best) | ✓ | ✗ (fullscreen only) | ✗ | hard to impl. |
| Keyboard nav (← → ESC) | ✓ | ✓ | ✓ (37/39/27 keys) | ✓ | impl. effort |
| ARIA / focus trap | ✓ (`trapFocus`,`returnFocus`) | ✓ (`role=dialog`, focus) | ✓ (`role=dialog`, aria-label, aria-* ) | ✓ (basic) | impl. effort |
| Counter / indicator | ✓ (`indexIndicator`) | ✓ | ✓ | ✓ | impl. effort |
| Image preloading | ✓ (`preload:[1,2]`) | ✓ (`preload:true`) | ✓ (`preload:2`) | basic | impl. effort |
| Thumbnail strip | ✗ (custom `registerElement` only) | ✗ (no built-in) | ✗ | ✗ | full control |
| CSS customizability | ✓ (CSS vars + elements) | ✓ (themeable SVG icons / skins) | limited | moderate | Tailwind-native |
| Requires image `w`/`h` attrs | yes (`data-pswp-width/height`) | no | no | no | n/a |
| Maintenance | v5.4.4 May 2024; v6 in early beta | **v3.3.1 Jan 2025** (active) | **v1.13.0 Nov 2025** (active) | 2.11.5 ~2025 (low activity) | n/a |
| GitHub stars | 25.2K | 2.5K | 2.5K | 4.5K | n/a |

---

## Integration with Django templates (the pattern that matters)

All four mature libraries share the **same, clean MPA pattern** — progressive enhancement on
server-rendered HTML. Django renders the gallery; JS only "enhances" it, so no image data is ever
passed into JS by hand:

```django
{# detail.html — rendered server-side, urls/alt from ORM #}
{% if ad.images.all %}
  <div id="ad-gallery" class="glightbox-gallery">
    {% for image in ad.images.all %}
      <a href="{{ image.image_url }}"
         {# PhotoSwipe: add data-pswp-width/height for best layout; GLightbox/baguetteBox: optional #}
         data-title="{% trans "Photo" %} {{ forloop.counter }} {% trans "for" %} {{ ad|get_title:LANGUAGE_CODE }}">
        <img src="{{ image.thumbnail_large_url|default:image.image_url }}"
             alt="{% trans "Photo" %} {{ forloop.counter }} {% trans "for" %} {{ ad|get_title:LANGUAGE_CODE }}"
             class="w-full h-64 object-cover rounded-lg"
             loading="lazy" width="1280" height="960">
      </a>
    {% endfor %}
  </div>
{% endif %}
```

```django
{# at end of body — CDN + tiny init, mirrors the existing htmx script-tag style #}
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/glightbox@3.3.1/dist/css/glightbox.min.css">
<script src="https://cdn.jsdelivr.net/npm/glightbox@3.3.1/dist/js/glightbox.min.js"></script>
<script>
  document.addEventListener('DOMContentLoaded', function () {
    GLightbox({ selector: '.glightbox-gallery a' });
  });
</script>
```

Key point: **image URLs and alt text come straight from the Django template context** (the `Ad`/
`Image` ORM rows), not from JS data structures. The JS init is a single selector call. This is fully
HTMX-friendly: the gallery markup is server-rendered (not fetched via HTMX), while HTMX continues to
own only the dynamic search/autocomplete/pagination fragments — clean separation of concerns.

### HTMX MPA + lightbox: server-rendered enhancement (not pure client-side)
Verified best practice (matches PhotoSwipe's own docs — "provides an alternative way to view the
content", link-to-image as fallback) and the existing `list.html` inline-`<script>` convention:
- Render the gallery as real `<a href><img>` links server-side ⇒ works with JS disabled, indexed by
  crawlers, instant first paint.
- Enhance with one `DOMContentLoaded` script ⇒ no blocking, no framework runtime conflict with htmx.
- No need to hydrate a SPA view; htmx keeps paging/filtering as server HTML fragments.

### Modern gallery UX pattern checklist
- modal overlay (fixed, high z-index, tap-outside / ESC to close) ✓ all mature libs
- main viewer + thumbnail strip — **none of the libraries include this natively**; PhotoSwipe can build
  it via `pswp.ui.registerElement`, otherwise it's arrows + counter. For 1–5 ad photos, arrow
  navigation + counter is the standard, lighter pattern.
- swipe gestures + pinch-to-zoom + pan ✓ PhotoSwipe / GLightbox (baguetteBox has swipe but no zoom)
- keyboard nav + ESC + focus trap ✓ all mature libs
- counter ✓ all

---

## Ranked recommendation (top 3)

### 1. GLightbox v3.3.1 — RECOMMENDED
**Why:** best fit for *this* project. Ships a global UMD build usable with a plain `<script>` tag
(matching the existing `unpkg`/CDN pattern for htmx — no `type="module"` needed), **0 dependencies**,
~15 KB gzipped, MIT, and **actively maintained** (v3.3.1, Jan 2025; weekly downloads ~87k). It has
everything the brief requires: mobile touch swipe, **pinch-to-zoom + pan** (`zoomable:true`,
`draggable:true`), keyboard navigation + ARIA dialog semantics + focus handling, a slide counter,
configurable preload, loop, and a themeable CSS file with SVG icons injected by JS (no extra assets to
serve). Gallery grouping via `data-gallery`. Easy Django integration is the 3-line pattern above.
**Weakness:** no native thumbnail strip (only arrow nav + counter) — acceptable for 1–5 photos; and its
own CSS file is separate from Tailwind (fine, the modal is black-overlay which is conventional).

### 2. PhotoSwipe v5.4.4 — best UX, more weight
**Why choose it:** gold-standard zoom/gestures, deep configurability, responsive `srcset` support,
dynamic import of core (lazy-loads the big module only on first open — helps initial size), 25K stars,
MIT. **Weaknesses:** largest bundle (~17 KB gzipped + CSS + core), and **requires image dimensions**
(`data-pswp-width`/`data-pswp-height`) — you'd add a Django template tag for that. The recommended
CDN path is ESM (`type="module"` + dynamic `import()`), a slight deviation from the project's plain
script-tag style (a UMD fallback exists but is less documented). Last release May 2024; v6 is in early
beta, so v5 is stable-but-maturing. Best when zooming/panning quality is the top priority and you can
supply dimensions.

### 3. baguetteBox v1.13.0 — smallest, but missing zoom
**Why consider it:** tiny (~3.2 KB gzipped), 0 deps, MIT, **recently released (Nov 2025)**, UMD global
build, swipe + keyboard + ARIA `role="dialog"` + captions + responsive `data-at-*` image sets + built-in
preload(2) + CSS3 transitions with inline SVG arrows (no asset files). **Weaknesses:** **no
pinch-to-zoom / image pan** (only a fullscreen button) — a real loss for classifieds photos where buyers
want to inspect detail; limited CSS theming (harder to restyle than GLightbox/PhotoSwipe). Good only if
zoom is explicitly out of scope.

### (Eliminated) Lightbox2 v2.11.5
Tiny own code but **hard jQuery dependency** — the project has no jQuery and adding ~30 KB gzipped
plus a second framework just to "scroll through pictures" violates the dependency-free constraint. Also
lacks touch swipe/zoom on mobile. Not recommended.

### (Situational) Custom vanilla JS (~50–150 lines)
Zero bundle, perfect Tailwind/CSS control, full Progressive Enhancement. Viable *only* if the team can
own pinch-to-zoom + pan + focus trap + swipe + a11y. Pinch-zoom with pan is the hard part (gesture
math + CSS `touch-action`); getting it right on iOS/desktop is ~100+ lines and easy to regress.
Recommended **only** as a fallback if the added bundle of a library is truly unacceptable and zoom
quality is not critical (e.g., skip zoom, just do modal + swipe + keyboard + arrows — that's the
~60-line "easy" version).

---

## Final recommendation
Adopt **GLightbox v3.3.1** (CDN global build, 0 deps, ~15 KB gzipped, actively maintained). It matches
the existing CDN script-tag loading style, has pinch-to-zoom + pan + swipe + keyboard + ARIA + counter
+ preload out of the box, and integrates with Django templates via the server-rendered `<a><img>`
gallery + a one-selector `GLightbox()` init — no image data crossing into JS. Drop-in replacement for
the static photo grid in `detail.html` (and reusable on the list thumbnails). Re-evaluate only if you
later need a real thumbnail strip or want to shave bytes below 15 KB (then pick baguetteBox and drop
the zoom requirement).
