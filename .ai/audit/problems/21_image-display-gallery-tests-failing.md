---
id: 21_image-display-gallery-tests-failing
related_spec: .ai/problems/10_image-display_spec.md
related_plan: .ai/plans/34_image-display_plan.md
priority: High
status: Open
date: 2026-08-25
---

# Problem: Ad gallery/image-display tests failing (WIP not yet ready)

## Description

Two tests in `src/backend/apps/ads/tests/test_gallery_markup.py` fail during the
fast-gate suite run (unrelated to the i18n plans 33/34-category/35):

1. `ERROR at setup of test_static_grid_renders_without_js` —
   `fixture 'self' not found` at line 175. The test declares `self` as a fixture
   argument, which pytest cannot resolve. This is a structural bug in the test
   (likely a class/instance mis-declaration introduced while restructuring the
   gallery markup assertions).

2. `FAILED TestGalleryMarkup::test_detail_gallery_has_slider_structure` —
   `assert 'Previous image' in content` fails: the rendered ad detail page does
   not contain the expected slider navigation string.

## Affected modules

- `src/backend/apps/ads/tests/test_gallery_markup.py`
- `src/backend/templates/ads/detail.html` (gallery/slider markup section)
- Related static assets under `src/theme/static/theme/js/`

## Risk

Medium. These failures currently keep the fast-gate CI red for the repository as a
whole, even though the i18n suites (plans 33/34/35) are green. They must not be
merged/pushed before they are resolved.

## Root cause

The gallery markup and its tests belong to the **image-display** work
(spec `10_image-display_spec.md`, plan `34_image-display_plan.md`), which is still
in progress in the shared working tree:
- `detail.html` was rewritten with a slider/thumbnail gallery (`Previous image` /
  `Next image` / `Select image` controls, GLightbox group anchors).
- `test_gallery_markup.py` was updated to assert the new structure but is not yet
  consistent with the rendered output (missing/renamed strings, invalid fixture
  signature).

These changes are unrelated to the i18n plans 33 (`08_multilingual-dev_spec.md`),
34-category (`09_category-city-i18n_rendering_spec.md`), and 35
(`i18n-translation-pipeline-gap-analysis.md`).

## Architectural impact

None for the i18n architecture. The gallery work is confined to the ads
detail/grid rendering path and its own test module.

## Suggested direction

Resolve within the image-display plan (`34_image-display_plan.md`):
1. Fix the `fixture 'self' not found` error in `test_static_grid_renders_without_js`
   (remove the invalid `self` fixture parameter).
2. Align `test_detail_gallery_has_slider_structure` with the actual rendered gallery
   markup in `detail.html`, or adjust the template to emit the asserted text.
3. Run `make test` (fast gate) and confirm 0 failures before committing.

This problem intentionally does **not** modify the i18n plans 33/34-category/35;
their implementation and tests are complete and passing.
