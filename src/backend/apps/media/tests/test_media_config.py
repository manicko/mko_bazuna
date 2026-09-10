"""Unit tests for ``MediaConfig.ready`` — ``MAX_IMAGE_PIXELS`` setting."""

from PIL import Image

import pytest

pytestmark = [pytest.mark.unit]


def test_max_image_pixels_is_set() -> None:
    """``MediaConfig.ready()`` sets ``MAX_IMAGE_PIXELS`` to twice the 2560² ceiling."""
    import apps.media as media_module
    from apps.media.apps import MediaConfig

    config = MediaConfig("apps.media", media_module)
    config.ready()

    assert Image.MAX_IMAGE_PIXELS == 2560 * 2560 * 2
