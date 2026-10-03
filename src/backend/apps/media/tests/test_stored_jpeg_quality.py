"""
Property test for the stored-original JPEG quality constant.

``07-MEDIA-011`` is a naming/traceability defect, not a behavioural one:
``strip_photo_exif`` used to save with no ``quality=`` and silently inherited
Pillow's implicit default.  The fix declares ``STORED_JPEG_QUALITY`` and passes
it to the save call.

This test asserts the **wiring** — that the value the save call actually
receives is the declared constant — and deliberately never asserts a literal
number.  Pinning ``== 75`` would re-create the defect in test form: it would
turn an inherited measurement into a contract and force the next maintainer to
edit the test whenever the constant changes.
"""

from __future__ import annotations

import io

from PIL import Image

from apps.media.services.filesystem import STORED_JPEG_QUALITY, strip_photo_exif


def _jpeg_bytes() -> bytes:
    """Return minimal valid JPEG bytes for the strip-and-save path."""
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), color="red").save(buffer, format="JPEG")
    return buffer.getvalue()


def test_strip_photo_exif_saves_at_the_declared_quality(monkeypatch):
    """The save call receives ``STORED_JPEG_QUALITY`` — read, never hard-coded."""
    captured: dict[str, object] = {}
    original_save = Image.Image.save

    def _spy_save(self, fp, *args, **kwargs):
        captured.update(kwargs)
        return original_save(self, fp, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", _spy_save)

    strip_photo_exif(_jpeg_bytes())

    assert captured.get("quality") == STORED_JPEG_QUALITY
