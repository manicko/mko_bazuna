---
id: BUG-01
title: ThumbnailService.generate_thumbnails raises UnidentifiedImageError but docstring says ValueError
status: open
severity: low
area: media/services/thumbnails.py
---

## Summary

`ThumbnailService.generate_thumbnails()` documents `ValueError` as the
exception for invalid image bytes, but Pillow's `Image.open()` raises
`PIL.UnidentifiedImageError` instead, which is not caught or converted.

## Location

- `src/backend/apps/media/services/thumbnails.py`, line 57 in the
  docstring of `generate_thumbnails()`.
- `src/backend/apps/media/services/thumbnails.py`, line 63 — the
  `Image.open()` call that raises `UnidentifiedImageError`.

## Impact

- Callers expecting `ValueError` would not catch the actual exception.
- The docstring is misleading.

## Suggested Fix

Either:

1. Update the docstring to document `UnidentifiedImageError` instead of
   `ValueError`, **or**

2. Wrap the `Image.open()` call in a try/except that converts
   `UnidentifiedImageError` to `ValueError` for a consistent public
   API.