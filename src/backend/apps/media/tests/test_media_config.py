"""Unit tests for ``MediaConfig.ready`` — ``MAX_IMAGE_PIXELS`` setting."""

import pytest
from PIL import Image

pytestmark = [pytest.mark.unit]


def test_max_image_pixels_is_set() -> None:
    """``MediaConfig.ready()`` sets ``MAX_IMAGE_PIXELS`` to twice the 2560² ceiling."""
    import apps.media as media_module
    from apps.media.apps import MediaConfig

    config = MediaConfig("apps.media", media_module)
    config.ready()

    assert Image.MAX_IMAGE_PIXELS == 2560 * 2560 * 2


def test_pre_delete_signal_registered_for_adimage() -> None:
    """``MediaConfig.ready()`` registers ``delete_adimage_files_on_delete`` on ``pre_delete``.

    Importing ``apps.media.signals`` inside ``ready()`` connects the handler via
    ``@receiver(pre_delete, sender=AdImage)``.  We verify both that listeners
    exist for the ``AdImage`` sender and that the specific handler function is
    among them.
    """
    from django.db.models.signals import pre_delete

    import apps.media as media_module
    from apps.ads.models import AdImage
    from apps.media.apps import MediaConfig
    from apps.media.signals import delete_adimage_files_on_delete

    config = MediaConfig("apps.media", media_module)
    config.ready()

    assert pre_delete.has_listeners(AdImage)
    sync_receivers, _ = pre_delete._live_receivers(AdImage)
    assert delete_adimage_files_on_delete in sync_receivers
